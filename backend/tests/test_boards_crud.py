"""Board library CRUD: create defaults, list ordering + summaries, rename,
delete, duplicate."""
from __future__ import annotations

from conftest import PNG_BYTES, upload_asset

EMPTY_SLIDE = {"text": "", "assets": [], "audio_stack": False}


# ------------------------------------------------------------------ #
#  Create                                                            #
# ------------------------------------------------------------------ #
def test_create_board_defaults(client):
    r = client.post("/api/boards", json={"name": "My Board"})
    assert r.status_code == 201
    b = r.json()
    assert b["name"] == "My Board"
    assert b["num_cols"] == 6
    assert b["num_rows"] == 5
    assert b["categories"] == [f"Category {i}" for i in range(1, 7)]
    assert b["row_values"] == [200, 400, 600, 800, 1000]
    assert len(b["cells"]) == 5
    for row_idx, row in enumerate(b["cells"]):
        assert len(row) == 6
        for cell in row:
            assert cell["value"] == b["row_values"][row_idx]
            assert cell["used"] is False
            assert cell["question_slide"] == EMPTY_SLIDE
            assert cell["answer_slide"] == EMPTY_SLIDE
    assert b["allow_negatives"] is True
    assert b["players"] == []
    assert b["id"]
    assert b["created_at"]
    assert b["updated_at"]


def test_create_board_blank_name_falls_back(client):
    r = client.post("/api/boards", json={"name": "   "})
    assert r.status_code == 201
    assert r.json()["name"] == "Untitled Board"


def test_create_board_default_body(client):
    r = client.post("/api/boards", json={})
    assert r.status_code == 201
    assert r.json()["name"] == "Untitled Board"


# ------------------------------------------------------------------ #
#  List: ordering + summary fields                                   #
# ------------------------------------------------------------------ #
def test_list_orders_by_updated_at_desc(client):
    a = client.post("/api/boards", json={"name": "A"}).json()
    client.post("/api/boards", json={"name": "B"})
    listing = client.get("/api/boards").json()
    assert [s["name"] for s in listing] == ["B", "A"]

    # Touching A bumps its updated_at to the top.
    client.patch(f"/api/boards/{a['id']}", json={"name": "A2"})
    listing = client.get("/api/boards").json()
    assert [s["name"] for s in listing] == ["A2", "B"]


def test_summary_fields_count_filled_cells(client, board):
    bid = board["id"]
    board["cells"][0][0]["question_slide"]["text"] = "A question"
    board["cells"][1][2]["answer_slide"]["assets"] = [
        {"path": "x.png", "asset_type": "image", "volume": 0.3}
    ]
    board["cells"][2][3]["question_slide"]["text"] = "   "  # whitespace ≠ filled
    assert client.put(f"/api/boards/{bid}", json=board).status_code == 200
    client.post(f"/api/boards/{bid}/players", json={"name": "Alice"})

    (s,) = client.get("/api/boards").json()
    assert s["id"] == bid
    assert s["name"] == "Test Board"
    assert s["filled_cells"] == 2
    assert s["total_cells"] == 30
    assert s["player_count"] == 1
    assert s["num_cols"] == 6
    assert s["num_rows"] == 5
    assert s["updated_at"]


# ------------------------------------------------------------------ #
#  Rename                                                            #
# ------------------------------------------------------------------ #
def test_rename_board(client, board):
    r = client.patch(f"/api/boards/{board['id']}", json={"name": "  New Name  "})
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"
    assert client.get(f"/api/boards/{board['id']}").json()["name"] == "New Name"


def test_rename_board_empty_422(client, board):
    assert client.patch(f"/api/boards/{board['id']}", json={"name": ""}).status_code == 422
    assert client.patch(f"/api/boards/{board['id']}", json={"name": "   "}).status_code == 422


# ------------------------------------------------------------------ #
#  Delete                                                            #
# ------------------------------------------------------------------ #
def test_delete_board_then_404(client, board):
    bid = board["id"]
    assert client.delete(f"/api/boards/{bid}").status_code == 204
    assert client.get(f"/api/boards/{bid}").status_code == 404
    assert client.delete(f"/api/boards/{bid}").status_code == 404


def test_get_unknown_board_404(client):
    assert client.get("/api/boards/deadbeef").status_code == 404
    assert client.get("/api/boards/not-a-real-id").status_code == 404


# ------------------------------------------------------------------ #
#  Duplicate                                                         #
# ------------------------------------------------------------------ #
def test_duplicate_copies_doc_and_assets(client, board, isolated_store):
    bid = board["id"]
    up = upload_asset(client, bid, "pic.png", PNG_BYTES).json()
    board = client.get(f"/api/boards/{bid}").json()
    board["cells"][0][0]["question_slide"]["assets"] = [
        {"path": up["path"], "asset_type": "image", "volume": 0.5}
    ]
    board["cells"][0][0]["question_slide"]["text"] = "Look at this"
    assert client.put(f"/api/boards/{bid}", json=board).status_code == 200

    r = client.post(f"/api/boards/{bid}/duplicate")
    assert r.status_code == 201
    dup = r.json()
    assert dup["id"] != bid
    assert dup["name"] == "Test Board (copy)"
    original = client.get(f"/api/boards/{bid}").json()
    assert dup["cells"] == original["cells"]
    assert dup["categories"] == original["categories"]
    assert dup["row_values"] == original["row_values"]

    # Asset files were physically copied to the duplicate's assets dir.
    r = client.get(f"/api/boards/{dup['id']}/assets/{up['path']}")
    assert r.status_code == 200
    assert r.content == PNG_BYTES
    dup_assets = isolated_store.assets_dir(dup["id"])
    assert (dup_assets / up["path"]).is_file()
