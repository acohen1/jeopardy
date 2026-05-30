"""
board.py — Jeopardy board data model with JSON save/load.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field

DEFAULT_VALUES = [200, 400, 600, 800, 1000]
DEFAULT_COLS = 6
DEFAULT_ROWS = 5


# ------------------------------------------------------------------ #
#  Slide-level data                                                   #
# ------------------------------------------------------------------ #
@dataclass
class SlideAsset:
    """One media file attached to a slide."""
    path: str = ""        # relative path inside assets/ folder
    asset_type: str = ""  # "image", "gif", "video", "audio", or ""
    volume: float = 0.3   # 0.0–1.0, used for audio mixing

    def to_dict(self) -> dict:
        d = {"path": self.path, "asset_type": self.asset_type}
        if self.asset_type in ("audio", "video"):
            d["volume"] = self.volume
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SlideAsset":
        atype = d.get("asset_type", "")
        # Videos predate per-asset volume; default them to full volume so
        # existing boards keep playing at 100%.
        default_vol = 1.0 if atype == "video" else 0.3
        return cls(path=d.get("path", ""),
                   asset_type=atype,
                   volume=d.get("volume", default_vol))


@dataclass
class Slide:
    """One page of content (used for both question and answer)."""
    text: str = ""
    assets: list = field(default_factory=list)  # list[SlideAsset]
    audio_stack: bool = False  # overlay multiple audio clips into one

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "assets": [a.to_dict() for a in self.assets],
            "audio_stack": self.audio_stack,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Slide":
        return cls(
            text=d.get("text", ""),
            assets=[SlideAsset.from_dict(a) for a in d.get("assets", [])],
            audio_stack=d.get("audio_stack", False),
        )

    # -- helpers --
    def image_assets(self) -> list[SlideAsset]:
        return [a for a in self.assets if a.asset_type in ("image", "gif")]

    def video_asset(self) -> SlideAsset | None:
        return next((a for a in self.assets if a.asset_type == "video"), None)

    def audio_assets(self) -> list[SlideAsset]:
        return [a for a in self.assets if a.asset_type == "audio"]

    def dominant_media_type(self) -> str:
        """Which renderer to use: 'video', 'audio_image', 'audio', 'image', or ''."""
        if self.video_asset():
            return "video"
        has_audio = bool(self.audio_assets())
        has_images = bool(self.image_assets())
        if has_audio and has_images:
            return "audio_image"
        if has_audio:
            return "audio"
        if has_images:
            return "image"
        return ""


# ------------------------------------------------------------------ #
#  Cell                                                               #
# ------------------------------------------------------------------ #
@dataclass
class Cell:
    """A single Jeopardy clue cell with question and answer slides."""
    question_slide: Slide = field(default_factory=Slide)
    answer_slide: Slide = field(default_factory=Slide)
    value: int = 0
    used: bool = False

    # Convenience properties for code that just needs the text
    @property
    def question(self) -> str:
        return self.question_slide.text

    @property
    def answer(self) -> str:
        return self.answer_slide.text

    def to_dict(self) -> dict:
        return {
            "question_slide": self.question_slide.to_dict(),
            "answer_slide": self.answer_slide.to_dict(),
            "value": self.value,
            "used": self.used,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Cell":
        # New format
        if "question_slide" in d:
            return cls(
                question_slide=Slide.from_dict(d["question_slide"]),
                answer_slide=Slide.from_dict(d.get("answer_slide", {})),
                value=d.get("value", 0),
                used=d.get("used", False),
            )
        # Legacy format — flat question/answer/asset_path/asset_type
        q_slide = Slide(text=d.get("question", ""))
        old_path = d.get("asset_path", "")
        old_type = d.get("asset_type", "")
        if old_path and old_type:
            q_slide.assets.append(SlideAsset(path=old_path, asset_type=old_type))
        a_slide = Slide(text=d.get("answer", ""))
        return cls(
            question_slide=q_slide,
            answer_slide=a_slide,
            value=d.get("value", 0),
            used=d.get("used", False),
        )


# ------------------------------------------------------------------ #
#  Board                                                              #
# ------------------------------------------------------------------ #
@dataclass
class Board:
    """
    Full Jeopardy board:
      - categories: list of column header strings (length == num_cols)
      - row_values:  list of dollar values per row (length == num_rows)
      - cells:       2-D list [row][col] of Cell objects
    """
    num_cols: int = DEFAULT_COLS
    num_rows: int = DEFAULT_ROWS
    categories: list = field(default_factory=lambda: [f"Category {i+1}" for i in range(DEFAULT_COLS)])
    row_values: list = field(default_factory=lambda: list(DEFAULT_VALUES))
    cells: list = field(default_factory=list)  # cells[row][col]
    allow_negatives: bool = True

    def __post_init__(self):
        if not self.cells:
            self._init_cells()

    def _init_cells(self):
        self.cells = [
            [Cell(value=self.row_values[r]) for _ in range(self.num_cols)]
            for r in range(self.num_rows)
        ]

    def reset_used(self):
        for row in self.cells:
            for cell in row:
                cell.used = False

    # ------------------------------------------------------------------ #
    #  Resize helpers                                                       #
    # ------------------------------------------------------------------ #
    def set_dimensions(self, num_rows: int, num_cols: int):
        """Resize board, preserving existing cell content."""
        old_cells = self.cells
        old_rows = self.num_rows
        old_cols = self.num_cols

        self.num_rows = num_rows
        self.num_cols = num_cols

        # Pad / trim categories
        while len(self.categories) < num_cols:
            self.categories.append(f"Category {len(self.categories)+1}")
        self.categories = self.categories[:num_cols]

        # Pad / trim row values
        while len(self.row_values) < num_rows:
            last = self.row_values[-1] if self.row_values else 200
            self.row_values.append(last + 200)
        self.row_values = self.row_values[:num_rows]

        new_cells = []
        for r in range(num_rows):
            row = []
            for c in range(num_cols):
                if r < old_rows and c < old_cols:
                    row.append(old_cells[r][c])
                else:
                    row.append(Cell(value=self.row_values[r]))
            new_cells.append(row)
        self.cells = new_cells

    # ------------------------------------------------------------------ #
    #  Save / Load                                                          #
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        return {
            "num_cols": self.num_cols,
            "num_rows": self.num_rows,
            "categories": self.categories,
            "row_values": self.row_values,
            "allow_negatives": self.allow_negatives,
            "cells": [[cell.to_dict() for cell in row] for row in self.cells],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Board":
        b = cls(
            num_cols=d.get("num_cols", DEFAULT_COLS),
            num_rows=d.get("num_rows", DEFAULT_ROWS),
            categories=d.get("categories", []),
            row_values=d.get("row_values", list(DEFAULT_VALUES)),
            allow_negatives=d.get("allow_negatives", True),
        )
        raw_cells = d.get("cells", [])
        if raw_cells:
            b.cells = [[Cell.from_dict(c) for c in row] for row in raw_cells]
        return b

    def save(self, json_path: str, assets_dir: str):
        os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, json_path: str) -> "Board":
        with open(json_path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return cls.from_dict(d)


# ------------------------------------------------------------------ #
#  Asset helpers                                                      #
# ------------------------------------------------------------------ #
def copy_asset_to_assets_dir(src_path: str, assets_dir: str) -> tuple[str, str]:
    """
    Copy a media file into assets_dir (if not already there).
    Returns (relative_path, asset_type).
    """
    os.makedirs(assets_dir, exist_ok=True)
    filename = os.path.basename(src_path)
    dest = os.path.join(assets_dir, filename)

    # Avoid overwriting with a different file — rename if needed
    if os.path.abspath(src_path) != os.path.abspath(dest):
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(dest) and not _same_file(src_path, dest):
            dest = os.path.join(assets_dir, f"{base}_{counter}{ext}")
            counter += 1
        if not os.path.exists(dest):
            shutil.copy2(src_path, dest)

    rel = os.path.basename(dest)
    ext = os.path.splitext(dest)[1].lower()
    asset_type = _ext_to_type(ext)
    return rel, asset_type


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.getsize(a) == os.path.getsize(b)
    except OSError:
        return False


def _ext_to_type(ext: str) -> str:
    if ext in {".gif"}:
        return "gif"
    if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
        return "image"
    if ext in {".mp4", ".webm", ".mov", ".avi", ".mkv"}:
        return "video"
    if ext in {".mp3", ".wav", ".ogg", ".flac", ".aac"}:
        return "audio"
    return ""
