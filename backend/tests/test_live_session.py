"""Live session: room lifecycle, joins, buzz arbitration, reconnect."""
from __future__ import annotations

import time


def _start(client, board):
    r = client.post("/api/session", json={"board_id": board["id"]})
    assert r.status_code == 200
    return r.json()


def _drain(sock, predicate, attempts=30):
    """Receive frames until one satisfies predicate (any message type).

    REST mutations reach sockets via a threadsafe async bridge, so the frame
    we want lands behind whatever broadcasts are already queued — poll,
    don't assert on the first frame."""
    for _ in range(attempts):
        msg = sock.receive_json()
        if predicate(msg):
            return msg
    raise AssertionError("expected message not received")


def test_create_and_inspect_session(client, board):
    s = _start(client, board)
    assert len(s["code"]) == 4 and s["code"].isupper()
    assert len(s["hostKey"]) == 32
    snap = client.get("/api/session").json()
    assert snap["code"] == s["code"]
    assert snap["buzzer"] == {"phase": "locked"}
    client.delete("/api/session")
    assert client.get("/api/session").status_code == 404


def test_player_join_and_wrong_code(client, board):
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": "XXXX", "name": "A"})
        assert ws.receive_json()["type"] == "error"
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "name": "Alex"})
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome" and welcome["token"]
        assert welcome["snapshot"]["participants"] == [{"name": "Alex", "connected": True}]


def test_buzz_arbitration_first_wins_and_lockout(client, board):
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as host, \
         client.websocket_connect("/api/ws") as p1, \
         client.websocket_connect("/api/ws") as p2:
        host.send_json({"type": "hello-host", "hostKey": s["hostKey"]})
        assert host.receive_json()["type"] == "welcome"
        p1.send_json({"type": "hello-player", "code": s["code"], "name": "One"})
        assert p1.receive_json()["type"] == "welcome"
        p2.send_json({"type": "hello-player", "code": s["code"], "name": "Two"})
        assert p2.receive_json()["type"] == "welcome"

        def drain_until(sock, predicate):
            for _ in range(20):
                msg = sock.receive_json()
                if msg["type"] == "snapshot" and predicate(msg["snapshot"]):
                    return msg["snapshot"]
            raise AssertionError("expected snapshot not received")

        # buzz while locked → ignored
        p1.send_json({"type": "buzz"})
        host.send_json({"type": "command", "command": "arm"})
        drain_until(host, lambda s2: s2["buzzer"]["phase"] == "armed")

        p1.send_json({"type": "buzz"})
        won = drain_until(host, lambda s2: s2["buzzer"]["phase"] == "won")
        assert won["buzzer"]["winner"] == "One"

        # second buzz recorded in order, winner unchanged
        p2.send_json({"type": "buzz"})
        both = drain_until(host, lambda s2: len(s2["buzzer"].get("order", [])) == 2)
        assert both["buzzer"]["winner"] == "One"
        assert both["buzzer"]["order"] == ["One", "Two"]

        # re-arm excluding winner: One is locked out, Two can win
        host.send_json({"type": "command", "command": "rearm-excluding-winner"})
        armed = drain_until(host, lambda s2: s2["buzzer"]["phase"] == "armed")
        assert armed["buzzer"]["lockedOut"] == ["One"]
        p1.send_json({"type": "buzz"})  # locked out — ignored
        p2.send_json({"type": "buzz"})
        won2 = drain_until(host, lambda s2: s2["buzzer"]["phase"] == "won")
        assert won2["buzzer"]["winner"] == "Two"

        # full reset clears lockouts
        host.send_json({"type": "command", "command": "reset-buzzer"})
        reset = drain_until(host, lambda s2: s2["buzzer"]["phase"] == "locked")
        assert reset["buzzer"] == {"phase": "locked"}


def test_reconnect_with_token_keeps_identity(client, board):
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "name": "Ray"})
        token = ws.receive_json()["token"]
    # socket closed → participant should show disconnected but persist
    snap = client.get("/api/session").json()
    assert snap["participants"] == [{"name": "Ray", "connected": False}]
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "token": token, "name": ""})
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome" and welcome["token"] == token
        assert welcome["snapshot"]["participants"] == [{"name": "Ray", "connected": True}]


def test_duplicate_name_rejected_only_while_connected(client, board):
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "name": "Kim"})
        assert ws.receive_json()["type"] == "welcome"
        with client.websocket_connect("/api/ws") as ws2:
            ws2.send_json({"type": "hello-player", "code": s["code"], "name": "Kim"})
            assert ws2.receive_json()["type"] == "error"
    # after disconnect the name can be reclaimed (new phone, same person)
    with client.websocket_connect("/api/ws") as ws3:
        ws3.send_json({"type": "hello-player", "code": s["code"], "name": "Kim"})
        assert ws3.receive_json()["type"] == "welcome"


def test_bad_host_key_rejected(client, board):
    _start(client, board)
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-host", "hostKey": "nope"})
        assert ws.receive_json()["type"] == "error"


def test_new_session_replaces_old(client, board):
    s1 = _start(client, board)
    s2 = _start(client, board)
    assert s2["code"] != s1["code"] or s2["hostKey"] != s1["hostKey"]
    assert client.get("/api/session").json()["code"] == s2["code"]


# ------------------------------------------------------------------ #
#  M2: scoreboard in snapshots + buzzer↔game integration              #
# ------------------------------------------------------------------ #
def test_join_auto_creates_board_player(client, board):
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "name": "Newbie"})
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"
        assert welcome["snapshot"]["scoreboard"] == [
            {"name": "Newbie", "score": 0, "connected": True}
        ]
        players = client.get(f"/api/boards/{board['id']}").json()["players"]
        assert players == [{"name": "Newbie", "score": 0}]


def test_join_adopts_existing_player_casing(client, board):
    r = client.post(f"/api/boards/{board['id']}/players", json={"name": "Sakura"})
    assert r.status_code == 201
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "name": "sakura"})
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"
        snap = welcome["snapshot"]
        assert snap["participants"] == [{"name": "Sakura", "connected": True}]
        assert snap["scoreboard"] == [
            {"name": "Sakura", "score": 0, "connected": True}
        ]
        names = [p["name"] for p in client.get(f"/api/boards/{board['id']}").json()["players"]]
        assert names == ["Sakura"]  # adopted, not duplicated


def test_award_broadcasts_result_to_all_sockets(client, board):
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as host, \
         client.websocket_connect("/api/ws") as p1, \
         client.websocket_connect("/api/ws") as p2:
        host.send_json({"type": "hello-host", "hostKey": s["hostKey"]})
        assert host.receive_json()["type"] == "welcome"
        p1.send_json({"type": "hello-player", "code": s["code"], "name": "One"})
        assert p1.receive_json()["type"] == "welcome"
        p2.send_json({"type": "hello-player", "code": s["code"], "name": "Two"})
        assert p2.receive_json()["type"] == "welcome"

        r = client.post(
            f"/api/boards/{board['id']}/players/One/award", json={"delta": 600}
        )
        assert r.status_code == 200
        for sock in (host, p1, p2):
            msg = _drain(sock, lambda m: m["type"] == "result")
            assert msg["player"] == "One" and msg["delta"] == 600
            row = next(x for x in msg["snapshot"]["scoreboard"] if x["name"] == "One")
            assert row["score"] == 600

        # deductions ride the same message, delta negative
        r = client.post(
            f"/api/boards/{board['id']}/players/One/award", json={"delta": -200}
        )
        assert r.status_code == 200
        for sock in (host, p1, p2):
            msg = _drain(sock, lambda m: m["type"] == "result")
            assert msg["player"] == "One" and msg["delta"] == -200
            row = next(x for x in msg["snapshot"]["scoreboard"] if x["name"] == "One")
            assert row["score"] == 400


def test_scoreboard_connected_reflects_phone_presence(client, board):
    r = client.post(f"/api/boards/{board['id']}/players", json={"name": "Bench"})
    assert r.status_code == 201
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "name": "Phone"})
        assert ws.receive_json()["type"] == "welcome"
        rows = {row["name"]: row for row in client.get("/api/session").json()["scoreboard"]}
        assert rows["Bench"]["connected"] is False
        assert rows["Phone"]["connected"] is True
    # phone gone → connected drops, player stays on the scoreboard
    rows = {row["name"]: row for row in client.get("/api/session").json()["scoreboard"]}
    assert rows["Phone"]["connected"] is False


def test_reconnect_token_does_not_duplicate_board_player(client, board):
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "name": "Ray"})
        token = ws.receive_json()["token"]
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "token": token, "name": "Ray"})
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome" and welcome["token"] == token
        players = client.get(f"/api/boards/{board['id']}").json()["players"]
        assert [p["name"] for p in players] == ["Ray"]
        snap = client.get("/api/session").json()
        assert [row["name"] for row in snap["scoreboard"]] == ["Ray"]


def test_scores_reset_broadcasts_zeroed_snapshot(client, board):
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as host, \
         client.websocket_connect("/api/ws") as p1:
        host.send_json({"type": "hello-host", "hostKey": s["hostKey"]})
        assert host.receive_json()["type"] == "welcome"
        p1.send_json({"type": "hello-player", "code": s["code"], "name": "One"})
        assert p1.receive_json()["type"] == "welcome"

        r = client.post(
            f"/api/boards/{board['id']}/players/One/award", json={"delta": 800}
        )
        assert r.status_code == 200
        # consume up to the award so a pre-award all-zero snapshot can't
        # satisfy the reset predicate below
        for sock in (host, p1):
            _drain(sock, lambda m: m["type"] == "result")

        r = client.post(f"/api/boards/{board['id']}/scores/reset")
        assert r.status_code == 200
        for sock in (host, p1):
            zeroed = _drain(
                sock,
                lambda m: m["type"] == "snapshot"
                and all(row["score"] == 0 for row in m["snapshot"]["scoreboard"]),
            )
            assert [row["name"] for row in zeroed["snapshot"]["scoreboard"]] == ["One"]


# ------------------------------------------------------------------ #
#  M2 hardening: roster, kick, join validation, autosave, rename      #
# ------------------------------------------------------------------ #
def test_roster_lookup_and_404s(client, board):
    client.delete("/api/session")  # singleton may carry a prior test's session
    assert client.get("/api/session/roster", params={"code": "XXXX"}).status_code == 404
    r = client.post(f"/api/boards/{board['id']}/players", json={"name": "Bench"})
    assert r.status_code == 201
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "name": "Phone"})
        assert ws.receive_json()["type"] == "welcome"
        r = client.get("/api/session/roster", params={"code": s["code"]})
        assert r.status_code == 200
        rows = {row["name"]: row for row in r.json()}
        assert rows["Bench"] == {"name": "Bench", "score": 0, "connected": False}
        assert rows["Phone"] == {"name": "Phone", "score": 0, "connected": True}
        wrong = "XXXX" if s["code"] != "XXXX" else "YYYY"
        assert client.get("/api/session/roster", params={"code": wrong}).status_code == 404


def test_kick_frees_name_and_invalidates_token(client, board):
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as host, \
         client.websocket_connect("/api/ws") as phone:
        host.send_json({"type": "hello-host", "hostKey": s["hostKey"]})
        assert host.receive_json()["type"] == "welcome"
        phone.send_json({"type": "hello-player", "code": s["code"], "name": "Zed"})
        old_token = phone.receive_json()["token"]
        r = client.post(f"/api/boards/{board['id']}/players/Zed/award", json={"delta": 200})
        assert r.status_code == 200
        _drain(host, lambda m: m["type"] == "result")

        host.send_json({"type": "command", "command": "kick", "target": "Zed"})
        # kicked socket gets the fatal error frame
        err = _drain(phone, lambda m: m["type"] == "error")
        assert err["message"] == "Removed by the host"
        # participant slot gone; board player + score untouched
        gone = _drain(
            host,
            lambda m: m["type"] == "snapshot" and m["snapshot"]["participants"] == [],
        )
        assert gone["snapshot"]["scoreboard"] == [
            {"name": "Zed", "score": 200, "connected": False}
        ]

        # name is free for a NEW socket immediately
        with client.websocket_connect("/api/ws") as ws2:
            ws2.send_json({"type": "hello-player", "code": s["code"], "name": "Zed"})
            w2 = ws2.receive_json()
            assert w2["type"] == "welcome" and w2["token"] != old_token
            reclaim_token = w2["token"]

        # the kicked device's token is dead: it rejoins as a fresh name-join
        # (reclaiming ws2's disconnected slot), never its old identity
        with client.websocket_connect("/api/ws") as ws3:
            ws3.send_json(
                {"type": "hello-player", "code": s["code"], "token": old_token, "name": "Zed"}
            )
            w3 = ws3.receive_json()
            assert w3["type"] == "welcome"
            assert w3["token"] != old_token and w3["token"] == reclaim_token


def test_join_rejects_path_separator_names(client, board):
    s = _start(client, board)
    for bad in ("Kim/Chae", "Kim\\Chae"):
        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"type": "hello-player", "code": s["code"], "name": bad})
            assert ws.receive_json()["type"] == "error"
    # rejected before any mutation: no participant, no board player
    assert client.get("/api/session").json()["participants"] == []
    assert client.get(f"/api/boards/{board['id']}").json()["players"] == []


def test_autosave_preserves_live_participants(client, board):
    draft = client.get(f"/api/boards/{board['id']}").json()  # predates everything
    r = client.post(f"/api/boards/{board['id']}/players", json={"name": "Bench"})
    assert r.status_code == 201
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as host, \
         client.websocket_connect("/api/ws") as phone:
        host.send_json({"type": "hello-host", "hostKey": s["hostKey"]})
        assert host.receive_json()["type"] == "welcome"
        phone.send_json({"type": "hello-player", "code": s["code"], "name": "Chae"})
        assert phone.receive_json()["type"] == "welcome"
        r = client.post(f"/api/boards/{board['id']}/players/Chae/award", json={"delta": 400})
        assert r.status_code == 200
        _drain(host, lambda m: m["type"] == "result")

        # stale editor PUT: participant survives with score, the
        # non-participant's deletion sticks
        r = client.put(f"/api/boards/{board['id']}", json=draft)
        assert r.status_code == 200
        assert [(p["name"], p["score"]) for p in r.json()["players"]] == [("Chae", 400)]
        snap = _drain(
            host,
            lambda m: m["type"] == "snapshot"
            and [row["name"] for row in m["snapshot"]["scoreboard"]] == ["Chae"],
        )
        assert snap["snapshot"]["scoreboard"][0]["score"] == 400


def test_rename_mid_won_keeps_winner_awardable(client, board):
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as host, \
         client.websocket_connect("/api/ws") as phone:
        host.send_json({"type": "hello-host", "hostKey": s["hostKey"]})
        assert host.receive_json()["type"] == "welcome"
        phone.send_json({"type": "hello-player", "code": s["code"], "name": "Kim"})
        assert phone.receive_json()["type"] == "welcome"
        host.send_json({"type": "command", "command": "arm"})
        phone.send_json({"type": "buzz"})
        _drain(
            host,
            lambda m: m["type"] == "snapshot" and m["snapshot"]["buzzer"]["phase"] == "won",
        )

        r = client.patch(f"/api/boards/{board['id']}/players/Kim", json={"name": "Chaewon"})
        assert r.status_code == 200
        snap = _drain(
            host,
            lambda m: m["type"] == "snapshot"
            and m["snapshot"]["buzzer"].get("winner") == "Chaewon",
        )["snapshot"]
        assert snap["participants"] == [{"name": "Chaewon", "connected": True}]
        assert snap["buzzer"]["order"] == ["Chaewon"]
        assert [row["name"] for row in snap["scoreboard"]] == ["Chaewon"]

        r = client.post(
            f"/api/boards/{board['id']}/players/Chaewon/award", json={"delta": 600}
        )
        assert r.status_code == 200
        msg = _drain(phone, lambda m: m["type"] == "result")
        assert msg["player"] == "Chaewon" and msg["delta"] == 600


def test_token_reconnect_recreates_deleted_board_player(client, board):
    s = _start(client, board)
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "name": "Ray"})
        token = ws.receive_json()["token"]
    r = client.delete(f"/api/boards/{board['id']}/players/Ray")
    assert r.status_code == 200
    # The notify bridge is async — WAIT (with real sleeps; a hot loop can
    # exhaust before the loop thread ever schedules the refresh) until the
    # cache reflects the delete, and fail loudly if it never does.
    for _ in range(100):
        if client.get("/api/session").json()["scoreboard"] == []:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("score cache never reflected the player delete")
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "hello-player", "code": s["code"], "token": token, "name": ""})
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome" and welcome["token"] == token
        assert welcome["snapshot"]["scoreboard"] == [
            {"name": "Ray", "score": 0, "connected": True}
        ]
        players = client.get(f"/api/boards/{board['id']}").json()["players"]
        assert players == [{"name": "Ray", "score": 0}]
