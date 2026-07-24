"""Turn order (board control): settings, sticky defaults, control endpoint."""
from __future__ import annotations

import time


def _rules(client, board_id, **overrides):
    body = {
        "allow_negatives": True,
        "turn_mode": "manual",
        "multi_award": "first",
        "first_pick": "random",
        **overrides,
    }
    r = client.put(f"/api/boards/{board_id}/settings", json=body)
    assert r.status_code == 200
    return r.json()


def _add_player(client, board_id, name):
    r = client.post(f"/api/boards/{board_id}/players", json={"name": name})
    assert r.status_code == 201
    return r.json()


def test_builtin_defaults(client):
    """No app defaults saved yet → classic game-show flow out of the box."""
    r = client.post("/api/boards", json={"name": "Fresh"})
    assert r.status_code == 201
    b = r.json()
    assert b["turn_mode"] == "first-correct"
    assert b["multi_award"] == "first"
    assert b["first_pick"] == "random"
    assert b["control_player"] is None


def test_settings_roundtrip(client, board):
    b = _rules(client, board["id"], turn_mode="sequential", first_pick="lowest")
    assert b["turn_mode"] == "sequential"
    assert b["first_pick"] == "lowest"
    assert b["multi_award"] == "first"


def test_partial_settings_put_keeps_other_rules(client, board):
    _rules(client, board["id"], turn_mode="sequential", first_pick="lowest")
    # The negatives toggle sends ONLY allow_negatives — rules must survive.
    r = client.put(
        f"/api/boards/{board['id']}/settings", json={"allow_negatives": False}
    )
    assert r.status_code == 200
    b = r.json()
    assert b["allow_negatives"] is False
    assert b["turn_mode"] == "sequential"
    assert b["first_pick"] == "lowest"


def test_settings_reject_unknown_mode(client, board):
    r = client.put(
        f"/api/boards/{board['id']}/settings",
        json={"allow_negatives": True, "turn_mode": "chaos"},
    )
    assert r.status_code == 422


def test_rules_become_defaults_for_new_boards(client, board):
    _rules(
        client, board["id"],
        turn_mode="first-correct", multi_award="last", first_pick="host",
        allow_negatives=False,
    )
    r = client.post("/api/boards", json={"name": "Next Game"})
    assert r.status_code == 201
    fresh = r.json()
    assert fresh["turn_mode"] == "first-correct"
    assert fresh["multi_award"] == "last"
    assert fresh["first_pick"] == "host"
    assert fresh["allow_negatives"] is False
    assert fresh["control_player"] is None


def test_control_set_clear_and_validation(client, board):
    _add_player(client, board["id"], "Alex")
    b = client.put(f"/api/boards/{board['id']}/control", json={"player": "Alex"}).json()
    assert b["control_player"] == "Alex"
    r = client.put(f"/api/boards/{board['id']}/control", json={"player": "Nobody"})
    assert r.status_code == 404
    b = client.put(f"/api/boards/{board['id']}/control", json={"player": None}).json()
    assert b["control_player"] is None


def test_control_follows_rename_and_clears_on_remove_and_reset(client, board):
    _add_player(client, board["id"], "Alex")
    client.put(f"/api/boards/{board['id']}/control", json={"player": "Alex"})

    b = client.patch(
        f"/api/boards/{board['id']}/players/Alex", json={"name": "Alexandra"}
    ).json()
    assert b["control_player"] == "Alexandra"

    b = client.delete(f"/api/boards/{board['id']}/players/Alexandra").json()
    assert b["control_player"] is None  # normalize_board drops dangling control

    _add_player(client, board["id"], "Chae")
    client.put(f"/api/boards/{board['id']}/control", json={"player": "Chae"})
    b = client.post(f"/api/boards/{board['id']}/scores/reset").json()
    assert b["control_player"] is None  # fresh game re-picks who starts


def test_editor_autosave_cannot_revert_play_rules(client, board):
    _add_player(client, board["id"], "Alex")
    _rules(client, board["id"], turn_mode="sequential")
    client.put(f"/api/boards/{board['id']}/control", json={"player": "Alex"})

    doc = client.get(f"/api/boards/{board['id']}").json()
    doc["turn_mode"] = "manual"  # stale/meddling editor payload
    doc["control_player"] = None
    doc["allow_negatives"] = False
    r = client.put(f"/api/boards/{board['id']}", json=doc)
    assert r.status_code == 200
    saved = r.json()
    assert saved["turn_mode"] == "sequential"
    assert saved["control_player"] == "Alex"
    assert saved["allow_negatives"] is True


def test_duplicate_clears_control_but_keeps_rules(client, board):
    _add_player(client, board["id"], "Alex")
    _rules(client, board["id"], turn_mode="sequential")
    client.put(f"/api/boards/{board['id']}/control", json={"player": "Alex"})
    copy = client.post(f"/api/boards/{board['id']}/duplicate").json()
    assert copy["turn_mode"] == "sequential"
    assert copy["control_player"] is None


def test_live_snapshot_carries_control(client, board):
    _add_player(client, board["id"], "Alex")
    r = client.post("/api/session", json={"board_id": board["id"]})
    assert r.status_code == 200
    assert client.get("/api/session").json()["control"] is None

    client.put(f"/api/boards/{board['id']}/control", json={"player": "Alex"})
    # the notify bridge is async — wait for the cache to catch up
    for _ in range(100):
        if client.get("/api/session").json()["control"] == "Alex":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("session snapshot never picked up control change")
