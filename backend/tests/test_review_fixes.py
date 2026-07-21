"""Regression tests for the post-review hardening fixes."""
from __future__ import annotations

import io
import json
import zipfile

from conftest import PNG_BYTES, upload_asset


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in entries.items():
            z.writestr(name, content)
    return buf.getvalue()


def _minimal_board_json(**overrides) -> bytes:
    d = {
        "num_cols": 1,
        "num_rows": 1,
        "categories": ["A"],
        "row_values": [100],
        "cells": [[{"question_slide": {"text": "q", "assets": [],
                    "audio_stack": False},
                    "answer_slide": {"text": "a", "assets": [],
                    "audio_stack": False},
                    "value": 100, "used": False}]],
    }
    d.update(overrides)
    return json.dumps(d).encode()


# ------------------------------------------------------------------ #
#  Zip import: non-media assets are never extracted (stored XSS fix)  #
# ------------------------------------------------------------------ #
def test_zip_import_skips_non_media_assets(client, isolated_store):
    zip_bytes = _zip_bytes({
        "board.json": _minimal_board_json(),
        "assets/evil.html": b"<script>alert(1)</script>",
        "assets/evil.svg": b"<svg onload=alert(1)></svg>",
        "assets/ok.png": PNG_BYTES,
    })
    r = client.post("/api/boards/import", files={"file": ("pkg.zip", zip_bytes)})
    assert r.status_code == 201
    bid = r.json()["id"]
    names = {p.name for p in isolated_store.assets_dir(bid).iterdir()}
    assert names == {"ok.png"}
    assert client.get(f"/api/boards/{bid}/assets/evil.html").status_code == 404


def test_zip_import_backslash_entry_names(client, isolated_store):
    zip_bytes = _zip_bytes({
        "board.json": _minimal_board_json(),
        "assets\\song.png": PNG_BYTES,  # Windows-archiver style separator
    })
    r = client.post("/api/boards/import", files={"file": ("pkg.zip", zip_bytes)})
    assert r.status_code == 201
    names = {p.name for p in isolated_store.assets_dir(r.json()["id"]).iterdir()}
    assert names == {"song.png"}


def test_malformed_cells_json_is_422_not_500(client):
    for payload in (
        json.dumps({"cells": [[None]]}).encode(),
        json.dumps({"cells": "x"}).encode(),
        json.dumps({"cells": [["nope"]]}).encode(),
    ):
        r = client.post("/api/boards/import", files={"file": ("b.json", payload)})
        assert r.status_code == 422, payload


def test_bom_json_imports(client):
    r = client.post(
        "/api/boards/import",
        files={"file": ("b.json", b"\xef\xbb\xbf" + _minimal_board_json())},
    )
    assert r.status_code == 201


def test_truncated_zip_member_is_422(client):
    good = _zip_bytes({"board.json": b"not json at all {{{"})
    r = client.post("/api/boards/import", files={"file": ("pkg.zip", good)})
    assert r.status_code == 422


# ------------------------------------------------------------------ #
#  Traversal-safe asset references (export / import)                  #
# ------------------------------------------------------------------ #
def test_export_ignores_traversal_asset_paths(client, board):
    bid = board["id"]
    upload_asset(client, bid, "real.png", PNG_BYTES)
    board["cells"][0][0]["question_slide"]["assets"] = [
        {"path": "../../../../secret.txt", "asset_type": "image", "volume": 0.3},
        {"path": "real.png", "asset_type": "image", "volume": 0.3},
    ]
    assert client.put(f"/api/boards/{bid}", json=board).status_code == 200
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/boards/{bid}/export").content))
    # normalize_board basenames the crafted path, so only plain names appear
    assert all("/" not in n.replace("assets/", "", 1) and ".." not in n
               for n in z.namelist())


# ------------------------------------------------------------------ #
#  PUT merges server game state (stale editor snapshot can't revert)  #
# ------------------------------------------------------------------ #
def test_put_preserves_server_scores_and_used(client, board):
    bid = board["id"]
    client.post(f"/api/boards/{bid}/players", json={"name": "Alex"})
    stale = client.get(f"/api/boards/{bid}").json()  # editor snapshot

    # game state advances after the snapshot
    client.post(f"/api/boards/{bid}/players/Alex/award", json={"delta": 400})
    client.put(f"/api/boards/{bid}/cells/0/0/used", json={"used": True})

    stale["categories"][0] = "Edited Category"  # the editor's actual edit
    r = client.put(f"/api/boards/{bid}", json=stale)
    assert r.status_code == 200
    saved = r.json()
    assert saved["categories"][0] == "Edited Category"
    assert saved["players"][0]["score"] == 400  # not reverted to 0
    assert saved["cells"][0][0]["used"] is True  # not reverted to False


def test_put_new_player_keeps_payload_score(client, board):
    bid = board["id"]
    doc = client.get(f"/api/boards/{bid}").json()
    doc["players"] = [{"name": "Fresh", "score": 123}]
    assert client.put(f"/api/boards/{bid}", json=doc).json()["players"] == [
        {"name": "Fresh", "score": 123}
    ]


# ------------------------------------------------------------------ #
#  Shape normalization on the live save path                          #
# ------------------------------------------------------------------ #
def test_put_with_inconsistent_dims_is_repaired(client, board):
    bid = board["id"]
    doc = client.get(f"/api/boards/{bid}").json()
    doc["num_rows"], doc["num_cols"], doc["cells"] = 3, 2, []
    saved = client.put(f"/api/boards/{bid}", json=doc).json()
    assert len(saved["cells"]) == 3 and len(saved["cells"][0]) == 2
    # cell lookups after the repair cannot 500
    assert client.put(f"/api/boards/{bid}/cells/2/1/used",
                      json={"used": True}).status_code == 200


def test_import_clamps_huge_dims(client):
    r = client.post(
        "/api/boards/import",
        files={"file": ("b.json", _minimal_board_json(num_rows=10**9, num_cols=10**9))},
    )
    assert r.status_code == 201
    b = r.json()
    assert b["num_rows"] <= 20 and b["num_cols"] <= 24


# ------------------------------------------------------------------ #
#  Player names cannot contain path separators                        #
# ------------------------------------------------------------------ #
def test_player_name_with_slash_rejected(client, board):
    bid = board["id"]
    for bad in ("AC/DC", "back\\slash"):
        r = client.post(f"/api/boards/{bid}/players", json={"name": bad})
        assert r.status_code == 422, bad


def test_put_sanitizes_player_names(client, board):
    bid = board["id"]
    doc = client.get(f"/api/boards/{bid}").json()
    doc["players"] = [{"name": "AC/DC", "score": 0}]
    saved = client.put(f"/api/boards/{bid}", json=doc).json()
    name = saved["players"][0]["name"]
    assert "/" not in name and "\\" not in name
    # and the game route can now address the player
    r = client.post(
        f"/api/boards/{bid}/players/{name}/award", json={"delta": 100}
    )
    assert r.status_code == 200


# ------------------------------------------------------------------ #
#  Concurrency plumbing                                               #
# ------------------------------------------------------------------ #
def test_concurrent_awards_do_not_lose_updates(client, board):
    import threading

    from fastapi.testclient import TestClient

    from app.main import app

    bid = board["id"]
    client.post(f"/api/boards/{bid}/players", json={"name": "P"})

    def hit():
        # One TestClient per thread for TRUE request parallelism (a shared
        # client partially serializes and hides races). TestClient re-raises
        # server exceptions in the sending thread — which is exactly how this
        # test caught the unlocked-read-vs-os.replace PermissionError race.
        with TestClient(app) as local:
            for _ in range(10):
                local.post(f"/api/boards/{bid}/players/P/award", json={"delta": 10})

    threads = [threading.Thread(target=hit) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert client.get(f"/api/boards/{bid}").json()["players"][0]["score"] == 400


def test_duplicate_copies_only_referenced_assets(client, board, isolated_store):
    bid = board["id"]
    upload_asset(client, bid, "used.png", PNG_BYTES)
    upload_asset(client, bid, "orphan.png", PNG_BYTES + b"x")
    doc = client.get(f"/api/boards/{bid}").json()
    doc["cells"][0][0]["question_slide"]["assets"] = [
        {"path": "used.png", "asset_type": "image", "volume": 0.3}
    ]
    client.put(f"/api/boards/{bid}", json=doc)
    copy = client.post(f"/api/boards/{bid}/duplicate").json()
    names = {p.name for p in isolated_store.assets_dir(copy["id"]).iterdir()}
    assert names == {"used.png"}
