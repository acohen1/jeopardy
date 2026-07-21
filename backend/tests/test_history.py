"""Score history, undo, and manual score-set."""
from __future__ import annotations


def _setup(client, board):
    bid = board["id"]
    client.post(f"/api/boards/{bid}/players", json={"name": "A"})
    client.post(f"/api/boards/{bid}/players", json={"name": "B"})
    return bid


def test_award_logs_event_with_note(client, board):
    bid = _setup(client, board)
    b = client.post(
        f"/api/boards/{bid}/players/A/award",
        json={"delta": 400, "note": "Cat 2 · $400"},
    ).json()
    assert len(b["history"]) == 1
    ev = b["history"][0]
    assert ev["player"] == "A" and ev["kind"] == "award"
    assert ev["delta"] == 400 and ev["before"] == 0 and ev["after"] == 400
    assert ev["note"] == "Cat 2 · $400"
    assert ev["ts"]


def test_set_score_logs_and_applies(client, board):
    bid = _setup(client, board)
    client.post(f"/api/boards/{bid}/players/A/award", json={"delta": 200})
    b = client.put(
        f"/api/boards/{bid}/players/A/score", json={"score": 1000, "note": "host fix"}
    ).json()
    assert b["players"][0]["score"] == 1000
    ev = b["history"][-1]
    assert ev["kind"] == "set" and ev["before"] == 200 and ev["after"] == 1000
    assert ev["delta"] == 800


def test_undo_walks_back_awards_and_sets(client, board):
    bid = _setup(client, board)
    client.post(f"/api/boards/{bid}/players/A/award", json={"delta": 200})
    client.post(f"/api/boards/{bid}/players/B/award", json={"delta": -600})
    client.put(f"/api/boards/{bid}/players/A/score", json={"score": 999})

    b = client.post(f"/api/boards/{bid}/history/undo").json()  # undo the set
    assert b["players"][0]["score"] == 200
    b = client.post(f"/api/boards/{bid}/history/undo").json()  # undo B's deduct
    assert b["players"][1]["score"] == 0
    b = client.post(f"/api/boards/{bid}/history/undo").json()  # undo A's award
    assert b["players"][0]["score"] == 0
    assert b["history"] == []


def test_undo_empty_history_409(client, board):
    bid = _setup(client, board)
    assert client.post(f"/api/boards/{bid}/history/undo").status_code == 409


def test_undo_after_player_removed_still_pops(client, board):
    bid = _setup(client, board)
    client.post(f"/api/boards/{bid}/players/A/award", json={"delta": 200})
    client.delete(f"/api/boards/{bid}/players/A")
    b = client.post(f"/api/boards/{bid}/history/undo").json()
    assert b["history"] == []


def test_reset_scores_clears_history(client, board):
    bid = _setup(client, board)
    client.post(f"/api/boards/{bid}/players/A/award", json={"delta": 200})
    b = client.post(f"/api/boards/{bid}/scores/reset").json()
    assert b["history"] == [] and b["players"][0]["score"] == 0


def test_editor_put_cannot_clobber_history(client, board):
    bid = _setup(client, board)
    stale = client.get(f"/api/boards/{bid}").json()  # snapshot before awards
    client.post(f"/api/boards/{bid}/players/A/award", json={"delta": 400})
    stale["categories"][0] = "Edited"
    b = client.put(f"/api/boards/{bid}", json=stale).json()
    assert len(b["history"]) == 1  # server history preserved
    assert b["players"][0]["score"] == 400


def test_history_capped_at_200(client, board):
    bid = _setup(client, board)
    for _ in range(205):
        client.post(f"/api/boards/{bid}/players/A/award", json={"delta": 1})
    b = client.get(f"/api/boards/{bid}").json()
    assert len(b["history"]) == 200
    assert b["players"][0]["score"] == 205  # cap trims the log, not the score


# ------------------------------------------------------------------ #
#  Bonus tiles                                                        #
# ------------------------------------------------------------------ #
def test_bonus_flag_persists_and_defaults_false(client, board):
    bid = board["id"]
    doc = client.get(f"/api/boards/{bid}").json()
    assert doc["cells"][0][0]["bonus"] is False  # default
    doc["cells"][1][2]["bonus"] = True
    saved = client.put(f"/api/boards/{bid}", json=doc).json()
    assert saved["cells"][1][2]["bonus"] is True
    assert client.get(f"/api/boards/{bid}").json()["cells"][1][2]["bonus"] is True


def test_legacy_import_defaults_bonus_false(client):
    import json as J

    legacy = {"num_cols": 1, "num_rows": 1, "categories": ["A"], "row_values": [100],
              "cells": [[{"question": "q", "answer": "a", "value": 100}]]}
    r = client.post("/api/boards/import",
                    files={"file": ("old.json", J.dumps(legacy).encode())})
    assert r.status_code == 201
    assert r.json()["cells"][0][0]["bonus"] is False
