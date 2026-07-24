"""Domain models + legacy-format migration.

The on-disk board document is the single source of truth for everything a
game needs: layout, slides, players, scores, and play-time state (used
cells, allow_negatives). This mirrors — and extends — the JSON format the
legacy PyQt app wrote, and `migrate_board_dict` accepts every historical
shape of that format.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AssetType = Literal["image", "gif", "video", "audio"]
VALID_ASSET_TYPES: tuple[str, ...] = ("image", "gif", "video", "audio")

DEFAULT_VALUES = [200, 400, 600, 800, 1000]
DEFAULT_COLS = 6
DEFAULT_ROWS = 5

# Hard bounds on board shape (frontend steppers stay within 10×12; these are
# generous so imports of odd-but-plausible files clamp instead of failing).
MAX_ROWS = 20
MAX_COLS = 24

# Extension → asset type. Mirrors legacy board._ext_to_type exactly.
EXT_TO_TYPE: dict[str, AssetType] = {
    ".gif": "gif",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".bmp": "image", ".webp": "image",
    ".mp4": "video", ".webm": "video", ".mov": "video",
    ".avi": "video", ".mkv": "video",
    ".mp3": "audio", ".wav": "audio", ".ogg": "audio",
    ".flac": "audio", ".aac": "audio",
}


class SlideAsset(BaseModel):
    path: str  # filename inside the board's assets/ dir
    asset_type: AssetType
    volume: float = Field(default=0.3, ge=0.0, le=1.0)


class Slide(BaseModel):
    text: str = ""
    assets: list[SlideAsset] = Field(default_factory=list)
    audio_stack: bool = False


class Cell(BaseModel):
    question_slide: Slide = Field(default_factory=Slide)
    answer_slide: Slide = Field(default_factory=Slide)
    value: int = 0
    used: bool = False
    # Bonus tile: looks normal on the play board, but opens
    # with a reveal splash + host wager instead of the flat value.
    bonus: bool = False


class Player(BaseModel):
    name: str
    score: int = 0


class ScoreEvent(BaseModel):
    """One scoring action, kept on the board for the history feed and undo.

    `before`/`after` snapshot the player's score around the action, so undo
    is a uniform "set score back to `before`" regardless of kind.
    """
    ts: str
    player: str
    kind: Literal["award", "set"]
    delta: int = 0
    before: int = 0
    after: int = 0
    note: str = ""  # e.g. "Category 3 · $600"


MAX_HISTORY = 200


# Turn order ("board control") rules — all host-selectable per board, with
# the last-used values persisted as app defaults for future boards.
TurnMode = Literal["manual", "first-correct", "sequential"]
MultiAwardRule = Literal["first", "last", "host"]  # first-correct mode only
FirstPick = Literal["random", "host", "lowest"]  # who starts (non-manual)


class Board(BaseModel):
    id: str
    name: str
    num_cols: int = DEFAULT_COLS
    num_rows: int = DEFAULT_ROWS
    categories: list[str] = Field(default_factory=list)
    row_values: list[int] = Field(default_factory=lambda: list(DEFAULT_VALUES))
    cells: list[list[Cell]] = Field(default_factory=list)
    allow_negatives: bool = True
    turn_mode: TurnMode = "first-correct"  # classic game-show flow out of the box
    multi_award: MultiAwardRule = "first"
    first_pick: FirstPick = "random"
    # Whose pick it is right now (game state, like scores — None until
    # assigned; always a current player name, normalize_board enforces).
    control_player: str | None = None
    players: list[Player] = Field(default_factory=list)
    history: list[ScoreEvent] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class BoardSummary(BaseModel):
    id: str
    name: str
    num_cols: int
    num_rows: int
    filled_cells: int
    total_cells: int
    player_count: int
    updated_at: str


def new_board(board_id: str, name: str, now: str) -> Board:
    """A fresh default board matching the legacy defaults (6×5, 200–1000)."""
    return Board(
        id=board_id,
        name=name,
        categories=[f"Category {i + 1}" for i in range(DEFAULT_COLS)],
        cells=[
            [Cell(value=DEFAULT_VALUES[r]) for _ in range(DEFAULT_COLS)]
            for r in range(DEFAULT_ROWS)
        ],
        created_at=now,
        updated_at=now,
    )


def slide_is_filled(slide: Slide) -> bool:
    return bool(slide.text.strip()) or bool(slide.assets)


def cell_is_filled(cell: Cell) -> bool:
    return slide_is_filled(cell.question_slide) or slide_is_filled(cell.answer_slide)


def summarize(board: Board) -> BoardSummary:
    flat = [c for row in board.cells for c in row]
    return BoardSummary(
        id=board.id,
        name=board.name,
        num_cols=board.num_cols,
        num_rows=board.num_rows,
        filled_cells=sum(1 for c in flat if cell_is_filled(c)),
        total_cells=len(flat),
        player_count=len(board.players),
        updated_at=board.updated_at,
    )


# ------------------------------------------------------------------ #
#  Legacy migration                                                   #
# ------------------------------------------------------------------ #
def _migrate_asset(d: dict) -> dict | None:
    atype = d.get("asset_type", "")
    if atype not in VALID_ASSET_TYPES:
        return None
    # Videos predate per-asset volume; default them to full volume
    # (mirrors legacy SlideAsset.from_dict).
    default_vol = 1.0 if atype == "video" else 0.3
    return {
        "path": d.get("path", ""),
        "asset_type": atype,
        "volume": d.get("volume", default_vol),
    }


def _migrate_slide(d: dict) -> dict:
    assets = [a for a in (_migrate_asset(x) for x in d.get("assets", [])) if a]
    return {
        "text": d.get("text", ""),
        "assets": assets,
        "audio_stack": d.get("audio_stack", False),
    }


def _migrate_cell(d: dict) -> dict:
    if "question_slide" in d:
        return {
            "question_slide": _migrate_slide(d["question_slide"]),
            "answer_slide": _migrate_slide(d.get("answer_slide", {})),
            "value": d.get("value", 0),
            "used": d.get("used", False),
            "bonus": d.get("bonus", False),
        }
    # Oldest format — flat question/answer/asset_path/asset_type
    q_slide: dict = {"text": d.get("question", ""), "assets": [], "audio_stack": False}
    old_path = d.get("asset_path", "")
    old_type = d.get("asset_type", "")
    if old_path and old_type in VALID_ASSET_TYPES:
        migrated = _migrate_asset({"path": old_path, "asset_type": old_type})
        if migrated:
            q_slide["assets"].append(migrated)
    return {
        "question_slide": q_slide,
        "answer_slide": {"text": d.get("answer", ""), "assets": [], "audio_stack": False},
        "value": d.get("value", 0),
        "used": d.get("used", False),
    }


def migrate_board_dict(d: dict, board_id: str, name: str, now: str) -> Board:
    """Build a Board from any historical board-JSON shape.

    Pads categories / row_values / cells to the declared dimensions the same
    way legacy Board.set_dimensions did, so slightly inconsistent files
    still load.
    """
    num_cols = max(1, min(MAX_COLS, int(d.get("num_cols", DEFAULT_COLS))))
    num_rows = max(1, min(MAX_ROWS, int(d.get("num_rows", DEFAULT_ROWS))))

    categories = [str(c) for c in d.get("categories", [])][:num_cols]
    while len(categories) < num_cols:
        categories.append(f"Category {len(categories) + 1}")

    row_values = [int(v) for v in d.get("row_values", DEFAULT_VALUES)][:num_rows]
    while len(row_values) < num_rows:
        # Legacy parity: pad from last + 200, with 200 as the "last" when the
        # list is empty — so an empty list pads 400, 600, … (board.py).
        last = row_values[-1] if row_values else 200
        row_values.append(last + 200)

    raw_cells = d.get("cells", [])
    cells: list[list[Cell]] = []
    for r in range(num_rows):
        raw_row = raw_cells[r] if r < len(raw_cells) else []
        row: list[Cell] = []
        for c in range(num_cols):
            if c < len(raw_row):
                row.append(Cell.model_validate(_migrate_cell(raw_row[c])))
            else:
                row.append(Cell(value=row_values[r]))
        cells.append(row)

    players = [
        Player(name=str(p.get("name", "")), score=int(p.get("score", 0)))
        for p in d.get("players", [])
        if str(p.get("name", "")).strip()
    ]

    return Board(
        id=board_id,
        name=d.get("name", name) or name,
        num_cols=num_cols,
        num_rows=num_rows,
        categories=categories,
        row_values=row_values,
        cells=cells,
        allow_negatives=d.get("allow_negatives", True),
        players=players,
        created_at=d.get("created_at", now) or now,
        updated_at=now,
    )


# ------------------------------------------------------------------ #
#  Normalization (every persisted board passes through this)          #
# ------------------------------------------------------------------ #
def _basename(name: str) -> str:
    """Plain filename component — strips any path separators a crafted or
    hand-edited document may carry (path-traversal guard)."""
    return name.replace("\\", "/").rsplit("/", 1)[-1].strip()


def normalize_board(board: Board) -> Board:
    """Clamp shape, pad/trim arrays to the declared dimensions, and sanitize
    names/paths — IN PLACE. Called on every write, so a document saved via
    the full-doc PUT can never disagree with its own dimensions (which would
    turn later cell lookups into 500s) or smuggle unsafe asset paths.
    """
    board.num_rows = max(1, min(MAX_ROWS, board.num_rows))
    board.num_cols = max(1, min(MAX_COLS, board.num_cols))

    board.categories = [str(c) for c in board.categories][: board.num_cols]
    while len(board.categories) < board.num_cols:
        board.categories.append(f"Category {len(board.categories) + 1}")

    board.row_values = list(board.row_values)[: board.num_rows]
    while len(board.row_values) < board.num_rows:
        last = board.row_values[-1] if board.row_values else 200
        board.row_values.append(last + 200)

    cells: list[list[Cell]] = []
    for r in range(board.num_rows):
        row = list(board.cells[r]) if r < len(board.cells) else []
        row = row[: board.num_cols]
        while len(row) < board.num_cols:
            row.append(Cell(value=board.row_values[r]))
        cells.append(row)
    board.cells = cells

    for row in board.cells:
        for cell in row:
            for slide in (cell.question_slide, cell.answer_slide):
                kept = []
                for a in slide.assets:
                    a.path = _basename(a.path)
                    if a.path:
                        kept.append(a)
                slide.assets = kept

    seen: set[str] = set()
    players: list[Player] = []
    for p in board.players:
        name = _basename(p.name)  # path separators break /players/{name} routes
        if name and name not in seen:
            seen.add(name)
            p.name = name
            players.append(p)
    board.players = players

    # Control must always name a current player (renames/removals/imports
    # can orphan it) — a dangling name would break turn highlights silently.
    if board.control_player is not None and not any(
        p.name == board.control_player for p in board.players
    ):
        board.control_player = None

    if len(board.history) > MAX_HISTORY:
        board.history = board.history[-MAX_HISTORY:]

    return board
