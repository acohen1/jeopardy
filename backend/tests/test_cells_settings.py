"""Play-time cell state (used flags) + board settings."""
from __future__ import annotations


def test_set_cell_used_true_then_false(client, board):
    bid = board["id"]
    r = client.put(f"/api/boards/{bid}/cells/1/2/used", json={"used": True})
    assert r.status_code == 200
    assert r.json()["cells"][1][2]["used"] is True
    # Only that cell changed.
    flat = [
        (ri, ci, c["used"])
        for ri, row in enumerate(r.json()["cells"])
        for ci, c in enumerate(row)
        if c["used"]
    ]
    assert flat == [(1, 2, True)]

    r = client.put(f"/api/boards/{bid}/cells/1/2/used", json={"used": False})
    assert r.status_code == 200
    assert r.json()["cells"][1][2]["used"] is False


def test_set_cell_used_out_of_range_404(client, board):
    bid = board["id"]
    assert client.put(f"/api/boards/{bid}/cells/5/0/used", json={"used": True}).status_code == 404
    assert client.put(f"/api/boards/{bid}/cells/0/6/used", json={"used": True}).status_code == 404
    assert client.put(f"/api/boards/{bid}/cells/-1/0/used", json={"used": True}).status_code == 404
    assert client.put(f"/api/boards/{bid}/cells/99/99/used", json={"used": True}).status_code == 404


def test_reset_used_clears_all(client, board):
    bid = board["id"]
    for row, col in ((0, 0), (2, 3), (4, 5)):
        client.put(f"/api/boards/{bid}/cells/{row}/{col}/used", json={"used": True})
    r = client.post(f"/api/boards/{bid}/cells/reset-used")
    assert r.status_code == 200
    assert all(not c["used"] for row in r.json()["cells"] for c in row)
    # Persisted.
    fetched = client.get(f"/api/boards/{bid}").json()
    assert all(not c["used"] for row in fetched["cells"] for c in row)


def test_settings_allow_negatives(client, board):
    bid = board["id"]
    assert board["allow_negatives"] is True
    r = client.put(f"/api/boards/{bid}/settings", json={"allow_negatives": False})
    assert r.status_code == 200
    assert r.json()["allow_negatives"] is False
    assert client.get(f"/api/boards/{bid}").json()["allow_negatives"] is False
    r = client.put(f"/api/boards/{bid}/settings", json={"allow_negatives": True})
    assert r.json()["allow_negatives"] is True
