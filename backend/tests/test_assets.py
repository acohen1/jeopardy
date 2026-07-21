"""Asset upload dedupe/rename semantics, serving (incl. Range), traversal."""
from __future__ import annotations

from conftest import MP3_BYTES, PNG_BYTES, upload_asset


# ------------------------------------------------------------------ #
#  Upload                                                            #
# ------------------------------------------------------------------ #
def test_upload_png_stored(client, board, isolated_store):
    bid = board["id"]
    r = upload_asset(client, bid, "pic.png", PNG_BYTES)
    assert r.status_code == 201
    body = r.json()
    assert body == {"path": "pic.png", "asset_type": "image"}
    assert (isolated_store.assets_dir(bid) / "pic.png").read_bytes() == PNG_BYTES


def test_upload_asset_types(client, board):
    bid = board["id"]
    assert upload_asset(client, bid, "anim.gif", PNG_BYTES).json()["asset_type"] == "gif"
    assert upload_asset(client, bid, "clip.mp4", PNG_BYTES).json()["asset_type"] == "video"
    assert upload_asset(client, bid, "song.mp3", MP3_BYTES).json()["asset_type"] == "audio"


def test_reupload_same_name_and_size_reuses_path(client, board, isolated_store):
    bid = board["id"]
    first = upload_asset(client, bid, "pic.png", PNG_BYTES).json()
    second = upload_asset(client, bid, "pic.png", PNG_BYTES).json()
    assert second["path"] == first["path"] == "pic.png"
    files = [f.name for f in isolated_store.assets_dir(bid).iterdir()]
    assert files == ["pic.png"]  # no pic_1.png


def test_same_name_different_size_gets_suffix(client, board, isolated_store):
    bid = board["id"]
    upload_asset(client, bid, "pic.png", PNG_BYTES)
    other = PNG_BYTES + b"different-length-content"
    r = upload_asset(client, bid, "pic.png", other)
    assert r.status_code == 201
    assert r.json()["path"] == "pic_1.png"
    assets = isolated_store.assets_dir(bid)
    assert (assets / "pic.png").read_bytes() == PNG_BYTES
    assert (assets / "pic_1.png").read_bytes() == other


def test_upload_unsupported_extension_422(client, board):
    r = upload_asset(client, board["id"], "notes.txt", b"hello")
    assert r.status_code == 422


def test_upload_empty_file_422(client, board):
    r = upload_asset(client, board["id"], "pic.png", b"")
    assert r.status_code == 422


def test_upload_to_unknown_board_404(client):
    r = upload_asset(client, "deadbeef", "pic.png", PNG_BYTES)
    assert r.status_code == 404


def test_upload_traversal_filename_is_sanitized(client, board, isolated_store):
    bid = board["id"]
    r = upload_asset(client, bid, "..\\evil.png", PNG_BYTES)
    assert r.status_code == 201
    assert r.json()["path"] == "evil.png"
    assets = isolated_store.assets_dir(bid)
    assert (assets / "evil.png").is_file()
    # Nothing escaped into the board dir or above.
    assert not (assets.parent / "evil.png").exists()
    assert not (assets.parent.parent / "evil.png").exists()


# ------------------------------------------------------------------ #
#  Serving                                                           #
# ------------------------------------------------------------------ #
def test_get_asset_200(client, board):
    bid = board["id"]
    upload_asset(client, bid, "song.mp3", MP3_BYTES)
    r = client.get(f"/api/boards/{bid}/assets/song.mp3")
    assert r.status_code == 200
    assert r.content == MP3_BYTES


def test_get_asset_range_206(client, board):
    bid = board["id"]
    upload_asset(client, bid, "song.mp3", MP3_BYTES)
    r = client.get(
        f"/api/boards/{bid}/assets/song.mp3", headers={"Range": "bytes=0-4"}
    )
    assert r.status_code == 206
    assert r.content == MP3_BYTES[:5]
    assert r.headers["content-range"] == f"bytes 0-4/{len(MP3_BYTES)}"


def test_get_missing_asset_404(client, board):
    assert client.get(f"/api/boards/{board['id']}/assets/nope.png").status_code == 404


def test_get_asset_traversal_does_not_escape(client, board):
    bid = board["id"]
    # board.json definitely exists one level above assets/ — a successful
    # traversal would serve it. Both encoded separators must fail.
    for name in ("..%2Fboard.json", "..%5Cboard.json", "..%2F..%2Fsecret.png"):
        r = client.get(f"/api/boards/{bid}/assets/{name}")
        assert r.status_code == 404, name
        assert b"question_slide" not in r.content


def test_store_asset_path_sanitizes_traversal(board, isolated_store):
    bid = board["id"]
    assets = isolated_store.assets_dir(bid).resolve()
    for name in ("../board.json", "..\\..\\secret.png", "/etc/passwd", "C:\\evil.png"):
        p = isolated_store.asset_path(bid, name)
        assert p.is_relative_to(assets), name


# ------------------------------------------------------------------ #
#  Orphaned-media report + tidy                                       #
# ------------------------------------------------------------------ #
def test_orphan_report_and_tidy(client, board, isolated_store):
    import os
    import time

    bid = board["id"]
    upload_asset(client, bid, "kept.png", PNG_BYTES)
    upload_asset(client, bid, "orphan_old.png", PNG_BYTES + b"x")
    upload_asset(client, bid, "orphan_fresh.png", PNG_BYTES + b"yy")

    doc = client.get(f"/api/boards/{bid}").json()
    doc["cells"][0][0]["question_slide"]["assets"] = [
        {"path": "kept.png", "asset_type": "image", "volume": 0.3}
    ]
    client.put(f"/api/boards/{bid}", json=doc)

    # Backdate one orphan past the safety window; the fresh one stays young.
    old_path = isolated_store.assets_dir(bid) / "orphan_old.png"
    stale = time.time() - 7200
    os.utime(old_path, (stale, stale))

    report = client.get("/api/boards/storage/orphans").json()
    assert report["files"] == 1 and report["bytes"] == old_path.stat().st_size

    freed = client.post("/api/boards/storage/tidy").json()
    assert freed["files"] == 1
    names = {p.name for p in isolated_store.assets_dir(bid).iterdir()}
    # referenced + fresh survive; only the old orphan is gone
    assert names == {"kept.png", "orphan_fresh.png"}
