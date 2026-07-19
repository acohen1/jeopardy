"""Players: add / remove / rename / award."""
from __future__ import annotations


def _players(board_json) -> dict[str, int]:
    return {p["name"]: p["score"] for p in board_json["players"]}


def test_add_player(client, board):
    r = client.post(f"/api/boards/{board['id']}/players", json={"name": "  Alice  "})
    assert r.status_code == 201
    assert _players(r.json()) == {"Alice": 0}


def test_add_duplicate_player_409(client, board):
    bid = board["id"]
    client.post(f"/api/boards/{bid}/players", json={"name": "Alice"})
    r = client.post(f"/api/boards/{bid}/players", json={"name": "Alice"})
    assert r.status_code == 409
    # Stripping applies before the duplicate check too.
    r = client.post(f"/api/boards/{bid}/players", json={"name": " Alice "})
    assert r.status_code == 409


def test_add_player_empty_422(client, board):
    bid = board["id"]
    assert client.post(f"/api/boards/{bid}/players", json={"name": ""}).status_code == 422
    assert client.post(f"/api/boards/{bid}/players", json={"name": "   "}).status_code == 422


def test_remove_player(client, board):
    bid = board["id"]
    client.post(f"/api/boards/{bid}/players", json={"name": "Alice"})
    client.post(f"/api/boards/{bid}/players", json={"name": "Bob"})
    r = client.delete(f"/api/boards/{bid}/players/Alice")
    assert r.status_code == 200
    assert _players(r.json()) == {"Bob": 0}


def test_rename_player(client, board):
    bid = board["id"]
    client.post(f"/api/boards/{bid}/players", json={"name": "Alice"})
    client.post(f"/api/boards/{bid}/players", json={"name": "Alice"})  # 409, ignored
    client.post(f"/api/boards/{bid}/players/Alice/award", json={"delta": 600})
    r = client.patch(f"/api/boards/{bid}/players/Alice", json={"name": "Alicia"})
    assert r.status_code == 200
    assert _players(r.json()) == {"Alicia": 600}  # score survives the rename


def test_rename_player_to_existing_409(client, board):
    bid = board["id"]
    client.post(f"/api/boards/{bid}/players", json={"name": "Alice"})
    client.post(f"/api/boards/{bid}/players", json={"name": "Bob"})
    r = client.patch(f"/api/boards/{bid}/players/Alice", json={"name": "Bob"})
    assert r.status_code == 409


def test_rename_player_empty_422_and_missing_404(client, board):
    bid = board["id"]
    client.post(f"/api/boards/{bid}/players", json={"name": "Alice"})
    assert (
        client.patch(f"/api/boards/{bid}/players/Alice", json={"name": "  "}).status_code
        == 422
    )
    assert (
        client.patch(f"/api/boards/{bid}/players/Nobody", json={"name": "X"}).status_code
        == 404
    )


def test_award_accumulates_positive_and_negative(client, board):
    bid = board["id"]
    client.post(f"/api/boards/{bid}/players", json={"name": "Alice"})
    r = client.post(f"/api/boards/{bid}/players/Alice/award", json={"delta": 400})
    assert _players(r.json()) == {"Alice": 400}
    r = client.post(f"/api/boards/{bid}/players/Alice/award", json={"delta": 600})
    assert _players(r.json()) == {"Alice": 1000}
    r = client.post(f"/api/boards/{bid}/players/Alice/award", json={"delta": -200})
    assert _players(r.json()) == {"Alice": 800}
    # Persisted, not just echoed.
    assert _players(client.get(f"/api/boards/{bid}").json()) == {"Alice": 800}


def test_award_missing_player_404(client, board):
    r = client.post(f"/api/boards/{board['id']}/players/Nobody/award", json={"delta": 100})
    assert r.status_code == 404


def test_reset_scores(client, board):
    bid = board["id"]
    for name in ("Alice", "Bob"):
        client.post(f"/api/boards/{bid}/players", json={"name": name})
    client.post(f"/api/boards/{bid}/players/Alice/award", json={"delta": 800})
    client.post(f"/api/boards/{bid}/players/Bob/award", json={"delta": -400})
    r = client.post(f"/api/boards/{bid}/scores/reset")
    assert r.status_code == 200
    assert _players(r.json()) == {"Alice": 0, "Bob": 0}
