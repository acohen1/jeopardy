"""File-based board store.

Layout:  <data_dir>/boards/<board_id>/board.json
         <data_dir>/boards/<board_id>/assets/<filename>

Deliberately a thin, swappable layer: everything the API needs goes through
BoardStore so a real database can replace it later without touching routers.

Concurrency: a single process-wide re-entrant lock serializes every
read-modify-write and file publish. FastAPI runs sync handlers in a
threadpool, so without it two concurrent requests (editor autosave + a
play-mode award, say) interleave writes and corrupt board.json.
"""
from __future__ import annotations

import io
import json
import os
import re
import secrets
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .models import (
    Board,
    BoardSummary,
    EXT_TO_TYPE,
    migrate_board_dict,
    new_board,
    normalize_board,
    summarize,
)

# Where legacy desktop-app assets might live on this machine — used to
# resolve media referenced by a bare .json import (no zip = no bundled assets).
LEGACY_ASSET_SEARCH_PATHS = [
    Path(os.environ.get("APPDATA", "")) / "Chaewon Jeopardy" / "assets",
    Path(__file__).resolve().parent.parent.parent / "legacy" / "assets",
]

# Upload / import guardrails (generous for local media, but bounded).
MAX_UPLOAD_BYTES = 1 * 1024**3  # 1 GiB per uploaded file
MAX_IMPORT_BYTES = 2 * 1024**3  # 2 GiB per save package
MAX_ZIP_MEMBER_BYTES = 1 * 1024**3  # claimed uncompressed size per member


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(name: str) -> str:
    """Strip any path components and characters unsafe for filenames."""
    name = os.path.basename(name.replace("\\", "/"))
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip()
    return name or "file"


def _is_safe_asset_name(name: str) -> bool:
    """True when the stored asset reference is a plain filename (no path
    tricks) — the only shape add_asset ever produces."""
    return bool(name) and name == _safe_filename(name) and name not in (".", "..")


class BoardNotFound(Exception):
    pass


class BoardStore:
    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            data_dir = os.environ.get(
                "JEOPARDY_DATA_DIR",
                Path(__file__).resolve().parent.parent / "data",
            )
        self.data_dir = Path(data_dir)
        self.boards_dir = self.data_dir / "boards"
        self.boards_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    #  Paths                                                             #
    # ------------------------------------------------------------------ #
    def _board_dir(self, board_id: str) -> Path:
        # ids are token_hex — but guard against traversal anyway
        if not re.fullmatch(r"[0-9a-f]{8}", board_id):
            raise BoardNotFound(board_id)
        return self.boards_dir / board_id

    def _board_path(self, board_id: str) -> Path:
        return self._board_dir(board_id) / "board.json"

    def board_exists(self, board_id: str) -> bool:
        try:
            return self._board_path(board_id).is_file()
        except BoardNotFound:
            return False

    def assets_dir(self, board_id: str) -> Path:
        d = self._board_dir(board_id) / "assets"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def asset_path(self, board_id: str, filename: str) -> Path:
        """Resolve an asset path, refusing anything outside the assets dir."""
        assets = self.assets_dir(board_id).resolve()
        p = (assets / _safe_filename(filename)).resolve()
        if not p.is_relative_to(assets):
            raise FileNotFoundError(filename)
        return p

    def _new_id(self) -> str:
        """Fresh id, retrying on the (unlikely) collision with an existing dir."""
        while True:
            board_id = secrets.token_hex(4)
            if not (self.boards_dir / board_id).exists():
                return board_id

    # ------------------------------------------------------------------ #
    #  CRUD                                                              #
    # ------------------------------------------------------------------ #
    def list_boards(self) -> list[BoardSummary]:
        out: list[BoardSummary] = []
        for d in sorted(self.boards_dir.iterdir()) if self.boards_dir.exists() else []:
            p = d / "board.json"
            if p.is_file():
                try:
                    out.append(summarize(self._read(p)))
                except Exception:
                    continue  # skip corrupt entries rather than break the library
        out.sort(key=lambda s: s.updated_at, reverse=True)
        return out

    def create_board(self, name: str) -> Board:
        with self._lock:
            board = new_board(self._new_id(), name.strip() or "Untitled Board", _now())
            self._write(board)
        return board

    def get_board(self, board_id: str) -> Board:
        p = self._board_path(board_id)
        if not p.is_file():
            raise BoardNotFound(board_id)
        return self._read(p)

    def save_board(self, board: Board) -> Board:
        with self._lock:
            if not self._board_path(board.id).is_file():
                raise BoardNotFound(board.id)
            board.updated_at = _now()
            self._write(board)
        return board

    def update_board(self, board_id: str, mutator: Callable[[Board], None]) -> Board:
        """Atomic read-modify-write under the store lock. All fine-grained
        game mutations go through here so concurrent updates never lose
        each other's changes."""
        with self._lock:
            board = self.get_board(board_id)
            mutator(board)
            board.updated_at = _now()
            self._write(board)
        return board

    def delete_board(self, board_id: str) -> None:
        with self._lock:
            d = self._board_dir(board_id)
            if not d.is_dir():
                raise BoardNotFound(board_id)
            shutil.rmtree(d)

    def duplicate_board(self, board_id: str) -> Board:
        with self._lock:
            src = self.get_board(board_id)
            now = _now()
            copy = src.model_copy(deep=True)
            copy.id = self._new_id()
            copy.name = f"{src.name} (copy)"
            copy.created_at = now
            copy.updated_at = now
            self._write(copy)
            # copy only the assets the board actually references
            src_assets = self.assets_dir(board_id)
            dst_assets = self.assets_dir(copy.id)
            for name in self.referenced_assets(src):
                f = src_assets / name
                if f.is_file():
                    shutil.copy2(f, dst_assets / name)
        return copy

    # ------------------------------------------------------------------ #
    #  Assets                                                            #
    # ------------------------------------------------------------------ #
    def add_asset(self, board_id: str, filename: str, content: bytes) -> tuple[str, str]:
        """Store an uploaded file; returns (stored_filename, asset_type).

        Mirrors legacy copy_asset_to_assets_dir semantics: an existing file
        with the same name and size is treated as the same file (reused);
        a name collision with different content is renamed base_1.ext, …
        """
        self.get_board(board_id)  # 404 if unknown board
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("File is too large (limit 1 GiB)")
        filename = _safe_filename(filename)
        ext = os.path.splitext(filename)[1].lower()
        asset_type = EXT_TO_TYPE.get(ext)
        if asset_type is None:
            raise ValueError(f"Unsupported file type: {ext or '(none)'}")

        with self._lock:
            assets = self.assets_dir(board_id)
            base, extension = os.path.splitext(filename)
            dest = assets / filename
            counter = 1
            while dest.exists() and dest.stat().st_size != len(content):
                dest = assets / f"{base}_{counter}{extension}"
                counter += 1
            if not dest.exists():
                dest.write_bytes(content)
        return dest.name, asset_type

    def referenced_assets(self, board: Board) -> list[str]:
        """Unique asset filenames referenced by the board's slides — filtered
        to plain safe filenames so a crafted asset path can never traverse
        outside the assets dir (export/import both build paths from these)."""
        seen: dict[str, None] = {}
        for row in board.cells:
            for cell in row:
                for slide in (cell.question_slide, cell.answer_slide):
                    for a in slide.assets:
                        if _is_safe_asset_name(a.path):
                            seen.setdefault(a.path)
        return list(seen)

    # ------------------------------------------------------------------ #
    #  Export / import (save packages)                                   #
    # ------------------------------------------------------------------ #
    def export_zip(self, board_id: str) -> bytes:
        board = self.get_board(board_id)
        assets = self.assets_dir(board_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(
                "board.json",
                json.dumps(board.model_dump(), indent=2, ensure_ascii=False),
            )
            for name in self.referenced_assets(board):
                p = assets / name
                if p.is_file():
                    z.write(p, f"assets/{name}")
        return buf.getvalue()

    def import_package(self, filename: str, content: bytes) -> Board:
        """Import a save package (.zip) or a bare board .json (incl. legacy).

        Anything malformed raises ValueError (the router maps it to 422)."""
        if len(content) > MAX_IMPORT_BYTES:
            raise ValueError("Save package is too large (limit 2 GiB)")
        fallback_name = os.path.splitext(_safe_filename(filename))[0] or "Imported Board"
        try:
            if zipfile.is_zipfile(io.BytesIO(content)):
                return self._import_zip(content, fallback_name)
            data = json.loads(content.decode("utf-8-sig"))
            if not isinstance(data, dict) or "cells" not in data:
                raise ValueError("JSON file does not look like a Jeopardy board")
            return self._import_json(data, fallback_name)
        except json.JSONDecodeError as e:
            # JSONDecodeError IS a ValueError — catch it first so users get
            # a friendly message, not "Expecting value: line 1 column 1".
            raise ValueError(
                "Not a valid save package (.zip) or board .json"
            ) from e
        except ValueError:
            raise
        except (zipfile.BadZipFile, KeyError, AttributeError, TypeError,
                UnicodeDecodeError) as e:
            raise ValueError(
                "Not a valid save package (.zip) or board .json"
            ) from e

    def _import_zip(self, content: bytes, fallback_name: str) -> Board:
        with self._lock:
            board_id = self._new_id()
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    try:
                        raw = json.loads(z.read("board.json").decode("utf-8-sig"))
                    except KeyError as e:
                        raise ValueError("Save package is missing board.json") from e
                    if not isinstance(raw, dict):
                        raise ValueError("board.json is not a board document")
                    board = migrate_board_dict(raw, board_id, fallback_name, _now())
                    # Extract assets FIRST so a malformed archive never leaves a
                    # half-imported board in the library; board.json goes last.
                    assets = self.assets_dir(board_id)
                    for info in z.infolist():
                        # Some Windows archivers emit backslash separators.
                        parts = info.filename.replace("\\", "/").split("/")
                        if len(parts) != 2 or parts[0] != "assets" or info.is_dir():
                            continue
                        safe = _safe_filename(parts[1])
                        ext = os.path.splitext(safe)[1].lower()
                        if ext not in EXT_TO_TYPE:
                            continue  # only real media — never .html/.svg/etc
                        if info.file_size > MAX_ZIP_MEMBER_BYTES:
                            raise ValueError(f"Asset '{safe}' exceeds the 1 GiB limit")
                        (assets / safe).write_bytes(z.read(info))
                    self._write(board)
            except Exception:
                shutil.rmtree(self._board_dir(board_id), ignore_errors=True)
                raise
        return board

    def _import_json(self, data: dict, fallback_name: str) -> Board:
        with self._lock:
            board = migrate_board_dict(data, self._new_id(), fallback_name, _now())
            self._write(board)
            # A bare .json has no bundled media — try to resolve referenced
            # assets from known legacy locations on this machine.
            assets = self.assets_dir(board.id)
            for name in self.referenced_assets(board):
                for search_dir in LEGACY_ASSET_SEARCH_PATHS:
                    candidate = search_dir / name
                    try:
                        if candidate.is_file():
                            shutil.copy2(candidate, assets / name)
                            break
                    except OSError:
                        continue
        return board

    # ------------------------------------------------------------------ #
    #  IO                                                                #
    # ------------------------------------------------------------------ #
    def _read(self, path: Path) -> Board:
        with open(path, "r", encoding="utf-8") as f:
            return Board.model_validate(json.load(f))

    def _write(self, board: Board) -> None:
        board = normalize_board(board)
        with self._lock:
            d = self._board_dir(board.id)
            d.mkdir(parents=True, exist_ok=True)
            path = d / "board.json"
            # Unique temp name: a fixed one lets two writers interleave into
            # the same file and publish corrupt JSON via os.replace.
            tmp = d / f"board.json.{secrets.token_hex(4)}.tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(board.model_dump(), f, indent=2, ensure_ascii=False)
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)


# Module-level singleton used by routers; tests construct their own store.
store = BoardStore()
