"""Export zip packages, zip round-trip import, and legacy bare-.json import."""
from __future__ import annotations

import io
import json
import zipfile

import app.storage as storage_module
from conftest import MP3_BYTES, PNG_BYTES, upload_asset


def _reference_asset(client, board_json, path, asset_type="image", volume=0.5):
    board_json = client.get(f"/api/boards/{board_json['id']}").json()
    board_json["cells"][0][0]["question_slide"]["assets"] = [
        {"path": path, "asset_type": asset_type, "volume": volume}
    ]
    r = client.put(f"/api/boards/{board_json['id']}", json=board_json)
    assert r.status_code == 200
    return r.json()


# ------------------------------------------------------------------ #
#  Export                                                            #
# ------------------------------------------------------------------ #
def test_export_zip_contains_board_and_only_referenced_assets(client, board):
    bid = board["id"]
    ref = upload_asset(client, bid, "pic.png", PNG_BYTES).json()
    upload_asset(client, bid, "orphan.mp3", MP3_BYTES)  # never referenced
    _reference_asset(client, board, ref["path"])

    r = client.get(f"/api/boards/{bid}/export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert set(z.namelist()) == {"board.json", "assets/pic.png"}
        doc = json.loads(z.read("board.json").decode("utf-8"))
        assert doc["id"] == bid
        assert doc["cells"][0][0]["question_slide"]["assets"][0]["path"] == "pic.png"
        assert z.read("assets/pic.png") == PNG_BYTES


def test_export_unknown_board_404(client):
    assert client.get("/api/boards/deadbeef/export").status_code == 404


# ------------------------------------------------------------------ #
#  Zip round-trip import                                             #
# ------------------------------------------------------------------ #
def test_import_zip_roundtrip(client, board, isolated_store):
    bid = board["id"]
    ref = upload_asset(client, bid, "pic.png", PNG_BYTES).json()
    _reference_asset(client, board, ref["path"])
    for name, delta in (("Alice", 800), ("Bob", -400)):
        client.post(f"/api/boards/{bid}/players", json={"name": name})
        client.post(f"/api/boards/{bid}/players/{name}/award", json={"delta": delta})
    exported = client.get(f"/api/boards/{bid}/export").content

    r = client.post(
        "/api/boards/import",
        files={"file": ("save.jeopardy.zip", exported, "application/zip")},
    )
    assert r.status_code == 201
    imported = r.json()
    assert imported["id"] != bid
    assert imported["name"] == "Test Board"
    assert [(p["name"], p["score"]) for p in imported["players"]] == [
        ("Alice", 800),
        ("Bob", -400),
    ]
    original = client.get(f"/api/boards/{bid}").json()
    assert imported["cells"] == original["cells"]
    assert imported["categories"] == original["categories"]
    assert imported["row_values"] == original["row_values"]

    # Assets restored on disk and servable.
    assert (isolated_store.assets_dir(imported["id"]) / "pic.png").is_file()
    r = client.get(f"/api/boards/{imported['id']}/assets/pic.png")
    assert r.status_code == 200
    assert r.content == PNG_BYTES


# ------------------------------------------------------------------ #
#  Legacy bare-.json import (oldest flat cell format)                #
# ------------------------------------------------------------------ #
def test_import_legacy_flat_json(client, monkeypatch, tmp_path, isolated_store):
    legacy_dir = tmp_path / "legacy_assets"
    legacy_dir.mkdir()
    (legacy_dir / "clip.mp4").write_bytes(b"legacy-video-bytes")
    monkeypatch.setattr(storage_module, "LEGACY_ASSET_SEARCH_PATHS", [legacy_dir])

    data = {
        "num_cols": 2,
        "num_rows": 1,
        "categories": ["Music", "Movies"],
        "row_values": [100],
        "cells": [
            [
                {
                    "question": "Q1",
                    "answer": "A1",
                    "asset_path": "clip.mp4",
                    "asset_type": "video",
                    "value": 100,
                },
                {
                    "question": "Q2",
                    "answer": "A2",
                    "asset_path": "song.mp3",
                    "asset_type": "audio",
                    "value": 100,
                },
            ]
        ],
    }
    r = client.post(
        "/api/boards/import",
        files={"file": ("old_board.json", json.dumps(data).encode(), "application/json")},
    )
    assert r.status_code == 201
    b = r.json()
    # No "name" in the JSON → falls back to the filename stem.
    assert b["name"] == "old_board"
    assert b["num_cols"] == 2
    assert b["num_rows"] == 1

    video_cell = b["cells"][0][0]
    assert video_cell["question_slide"]["text"] == "Q1"
    assert video_cell["answer_slide"]["text"] == "A1"
    assert video_cell["value"] == 100
    # Legacy assets predate per-asset volume: video defaults to 1.0.
    assert video_cell["question_slide"]["assets"] == [
        {"path": "clip.mp4", "asset_type": "video", "volume": 1.0}
    ]

    audio_cell = b["cells"][0][1]
    assert audio_cell["question_slide"]["text"] == "Q2"
    # ...while audio defaults to 0.3.
    assert audio_cell["question_slide"]["assets"] == [
        {"path": "song.mp3", "asset_type": "audio", "volume": 0.3}
    ]

    # clip.mp4 existed in the legacy search path → copied into the board.
    assert (isolated_store.assets_dir(b["id"]) / "clip.mp4").read_bytes() == (
        b"legacy-video-bytes"
    )
    # song.mp3 was not resolvable anywhere — reference kept, file absent.
    assert not (isolated_store.assets_dir(b["id"]) / "song.mp3").exists()


def test_import_junk_bytes_422(client):
    r = client.post(
        "/api/boards/import",
        files={"file": ("garbage.bin", b"\x00\x01\x02 definitely not json", "application/octet-stream")},
    )
    assert r.status_code == 422


def test_import_json_without_cells_422(client):
    for payload in (json.dumps({"name": "No Cells Here"}), json.dumps([1, 2, 3])):
        r = client.post(
            "/api/boards/import",
            files={"file": ("bad.json", payload.encode(), "application/json")},
        )
        assert r.status_code == 422, payload


def test_import_zip_without_board_json_422(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "not a save package")
    r = client.post(
        "/api/boards/import",
        files={"file": ("bad.zip", buf.getvalue(), "application/zip")},
    )
    assert r.status_code == 422
