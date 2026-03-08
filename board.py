"""
board.py — Jeopardy board data model with JSON save/load.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_VALUES = [200, 400, 600, 800, 1000]
DEFAULT_COLS = 6
DEFAULT_ROWS = 5


@dataclass
class Cell:
    """A single Jeopardy clue cell."""
    question: str = ""
    answer: str = ""
    value: int = 0
    asset_path: str = ""   # relative path inside assets/ folder
    asset_type: str = ""   # "image", "gif", "video", "audio", or ""
    used: bool = False
    blur: bool = False      # start with gaussian blur in play mode

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "value": self.value,
            "asset_path": self.asset_path,
            "asset_type": self.asset_type,
            "used": self.used,
            "blur": self.blur,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Cell":
        return cls(
            question=d.get("question", ""),
            answer=d.get("answer", ""),
            value=d.get("value", 0),
            asset_path=d.get("asset_path", ""),
            asset_type=d.get("asset_type", ""),
            used=d.get("used", False),
            blur=d.get("blur", False),
        )


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
        """
        Save board JSON. Any cell asset_path values are already relative to
        assets_dir — nothing extra to do if assets were copied at import time.
        """
        os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, json_path: str) -> "Board":
        with open(json_path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return cls.from_dict(d)


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
