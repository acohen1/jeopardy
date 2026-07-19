"""Unit tests for migrate_board_dict: padding + asset volume defaults."""
from __future__ import annotations

from app.models import migrate_board_dict

NOW = "2026-01-01T00:00:00+00:00"


def test_pads_short_categories_row_values_and_cells():
    d = {
        "num_cols": 4,
        "num_rows": 3,
        "categories": ["Only One"],
        "row_values": [100],
        "cells": [[{"question": "Q", "answer": "A", "value": 100}]],
    }
    b = migrate_board_dict(d, "abcd1234", "Fallback", NOW)
    assert b.categories == ["Only One", "Category 2", "Category 3", "Category 4"]
    assert b.row_values == [100, 300, 500]  # last + 200 per missing row
    assert len(b.cells) == 3
    assert all(len(row) == 4 for row in b.cells)
    # The one real cell survived migration.
    assert b.cells[0][0].question_slide.text == "Q"
    assert b.cells[0][0].answer_slide.text == "A"
    # Padded cells are empty and get their row's value.
    assert b.cells[0][3].value == 100
    assert b.cells[1][0].value == 300
    assert b.cells[2][3].value == 500
    assert not b.cells[1][1].question_slide.text
    assert not b.cells[1][1].question_slide.assets


def test_empty_row_values_pad_legacy_parity():
    # Legacy board.py set_dimensions: last = row_values[-1] if row_values
    # else 200, then append(last + 200) — an empty list pads 400, 600, …
    d = {"num_cols": 1, "num_rows": 3, "categories": [], "row_values": [], "cells": []}
    b = migrate_board_dict(d, "abcd1234", "Fallback", NOW)
    assert b.row_values == [400, 600, 800]
    assert b.categories == ["Category 1"]


def test_oversized_lists_are_truncated_to_declared_dims():
    d = {
        "num_cols": 2,
        "num_rows": 1,
        "categories": ["A", "B", "C", "D"],
        "row_values": [100, 200, 300],
        "cells": [],
    }
    b = migrate_board_dict(d, "abcd1234", "Fallback", NOW)
    assert b.categories == ["A", "B"]
    assert b.row_values == [100]


def test_slide_asset_volume_defaults_by_type():
    d = {
        "num_cols": 1,
        "num_rows": 1,
        "row_values": [100],
        "categories": ["Cat"],
        "cells": [
            [
                {
                    "question_slide": {
                        "text": "q",
                        "assets": [
                            {"path": "v.mp4", "asset_type": "video"},
                            {"path": "a.mp3", "asset_type": "audio"},
                            {"path": "i.png", "asset_type": "image", "volume": 0.8},
                            {"path": "junk", "asset_type": "weird"},
                        ],
                    },
                    "answer_slide": {"text": "a"},
                    "value": 100,
                }
            ]
        ],
    }
    b = migrate_board_dict(d, "abcd1234", "Fallback", NOW)
    assets = b.cells[0][0].question_slide.assets
    # Unknown asset_type is dropped entirely.
    assert [a.path for a in assets] == ["v.mp4", "a.mp3", "i.png"]
    # Missing volume: video → 1.0, audio → 0.3; explicit volume preserved.
    assert assets[0].volume == 1.0
    assert assets[1].volume == 0.3
    assert assets[2].volume == 0.8


def test_players_migrated_and_blank_names_dropped():
    d = {
        "num_cols": 1,
        "num_rows": 1,
        "cells": [],
        "players": [
            {"name": "Alice", "score": 700},
            {"name": "   ", "score": 5},
            {"name": "Bob"},
        ],
    }
    b = migrate_board_dict(d, "abcd1234", "Fallback", NOW)
    assert [(p.name, p.score) for p in b.players] == [("Alice", 700), ("Bob", 0)]


def test_name_and_timestamps_fall_back():
    b = migrate_board_dict({"cells": []}, "abcd1234", "Fallback Name", NOW)
    assert b.name == "Fallback Name"
    assert b.created_at == NOW
    assert b.updated_at == NOW
    # Declared name wins over the fallback.
    b = migrate_board_dict({"cells": [], "name": "Real Name"}, "abcd1234", "Fallback", NOW)
    assert b.name == "Real Name"
