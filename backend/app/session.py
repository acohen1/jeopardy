"""Live game session: room code, participants, and buzzer arbitration.

One active session per app process (the host's machine IS the server).
Everything is in-memory and async — WebSocket handlers own all mutation,
guarded by a single asyncio.Lock. The protocol is transport-agnostic on
purpose: a future remote-play relay forwards the same JSON messages.

Buzz fairness: the server's arrival order is law (LAN latency ~ms). While
armed, the first non-locked-out buzz wins; later buzzes are recorded in
`order` for the "also buzzed" display but change nothing.
"""
from __future__ import annotations

import asyncio
import secrets
import string
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from .models import Board, Player
from .storage import store

CODE_ALPHABET = string.ascii_uppercase

# False-start penalty (seconds): buzzing before the arm — or while still
# frozen from doing so — re-freezes YOUR buzzer, real-Jeopardy style. Mashing
# is therefore self-defeating; clean timing always beats it. The controller
# mirrors this constant for its local "Too soon" feedback.
FALSE_START_PENALTY = 0.5


def _room_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))


@dataclass
class Participant:
    token: str
    name: str
    socket: WebSocket | None = None
    # time.monotonic() until which this player's buzzes are ignored
    # (false-start penalty; 0 = never frozen).
    frozen_until: float = 0.0

    @property
    def connected(self) -> bool:
        return self.socket is not None


@dataclass
class Session:
    code: str
    board_id: str
    host_key: str
    participants: dict[str, Participant] = field(default_factory=dict)  # token →
    host_sockets: set[WebSocket] = field(default_factory=set)
    # buzzer
    armed: bool = False
    winner: str | None = None
    order: list[str] = field(default_factory=list)
    locked_out: set[str] = field(default_factory=set)
    # (name, score) for every board player, in board order — a cache of the
    # store (the source of truth), refreshed on join and by notify_scores()
    # whenever a game endpoint mutates scores. Keeps snapshot() IO-free.
    scores: list[tuple[str, int]] = field(default_factory=list)
    # Whose pick it is (board.control_player), cached with the scores.
    control: str | None = None

    def snapshot(self) -> dict[str, Any]:
        if self.winner is not None:
            buzzer: dict[str, Any] = {
                "phase": "won",
                "winner": self.winner,
                "order": list(self.order),
                "lockedOut": sorted(self.locked_out),
            }
        elif self.armed:
            buzzer = {"phase": "armed", "lockedOut": sorted(self.locked_out)}
        else:
            buzzer = {"phase": "locked"}
        connected = {p.name for p in self.participants.values() if p.connected}
        return {
            "code": self.code,
            "boardId": self.board_id,
            "participants": [
                {"name": p.name, "connected": p.connected}
                for p in self.participants.values()
            ],
            # Every board player (phones or not) — scores + phone presence.
            "scoreboard": [
                {"name": name, "score": score, "connected": name in connected}
                for name, score in self.scores
            ],
            "control": self.control,
            "buzzer": buzzer,
        }


def _read_board_view(board_id: str) -> tuple[list[tuple[str, int]], str | None]:
    """(players as (name, score) in board order, control_player) — the live
    slice of the board a session mirrors; ([], None) if the board is gone."""
    try:
        board = store.get_board(board_id)
    except Exception:
        return [], None
    return [(p.name, p.score) for p in board.players], board.control_player


class SessionManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._session: Session | None = None
        # Captured on session create so sync game endpoints (threadpool) can
        # schedule broadcasts onto the server's event loop.
        self._loop: asyncio.AbstractEventLoop | None = None

    # ---------------------------------------------------------------- #
    #  Lifecycle (REST)                                                #
    # ---------------------------------------------------------------- #
    async def create(self, board_id: str) -> dict[str, Any]:
        async with self._lock:
            self._loop = asyncio.get_running_loop()
            # Starting a new session replaces any previous one.
            if self._session is not None:
                await self._broadcast_raw({"type": "ended"})
            scores, control = _read_board_view(board_id)
            self._session = Session(
                code=_room_code(),
                board_id=board_id,
                host_key=secrets.token_hex(16),
                scores=scores,
                control=control,
            )
            return {
                "code": self._session.code,
                "hostKey": self._session.host_key,
                "boardId": board_id,
            }

    async def end(self) -> None:
        async with self._lock:
            if self._session is None:
                return
            await self._broadcast_raw({"type": "ended"})
            self._session = None

    async def peek(self) -> dict[str, Any] | None:
        async with self._lock:
            return self._session.snapshot() if self._session else None

    async def roster(self, code: str) -> list[dict[str, Any]] | None:
        """Pre-join peek by room code: the scoreboard with phone-presence.
        Lets the join screen offer "who are you?" — connected names are
        claimed; disconnected ones are selectable (that's also how a dead
        phone rejoins as itself). None = no session / wrong code."""
        async with self._lock:
            s = self._session
            if s is None or code.strip().upper() != s.code:
                return None
            return s.snapshot()["scoreboard"]

    # ---------------------------------------------------------------- #
    #  WebSocket attach/detach                                         #
    # ---------------------------------------------------------------- #
    async def attach_host(self, socket: WebSocket, host_key: str) -> dict | None:
        """Attach; returns the snapshot for the welcome message, or None."""
        async with self._lock:
            s = self._session
            if s is None or host_key != s.host_key:
                return None
            s.host_sockets.add(socket)
            # Others learn of the (re)connect; the joiner gets the snapshot
            # inside its welcome — guaranteeing welcome arrives first.
            await self._broadcast(exclude=socket)
            return s.snapshot()

    async def attach_player(
        self, socket: WebSocket, code: str, name: str, token: str | None
    ) -> tuple[str, dict] | None:
        """Join (or reconnect). Returns (token, snapshot), or None."""
        async with self._lock:
            s = self._session
            if s is None or code.strip().upper() != s.code:
                return None
            name = name.strip()
            if "/" in name or "\\" in name:
                # Mirrors game.py _clean_player_name: normalize_board would
                # silently rewrite such a name on write, desyncing the
                # participant from its board player (winner unawardable).
                return None
            # Participants ARE scoreboard players: adopt the casing of an
            # existing board player ("sakura" joins as "Sakura") so award
            # routing by name is exact.
            match = next(
                (n for n, _ in s.scores if n.lower() == name.lower()), None
            )
            if match is not None:
                name = match
            if token and token in s.participants:
                # Reconnect: keep identity, swap the socket.
                p = s.participants[token]
                p.socket = socket
                name = p.name  # identity comes from the token, not the hello
            else:
                if not name or any(
                    p.name == name and p.connected for p in s.participants.values()
                ):
                    return None  # empty, or actively claimed by someone else
                # Reclaim a disconnected participant slot with the same name.
                existing = next(
                    (p for p in s.participants.values() if p.name == name), None
                )
                if existing is not None:
                    existing.socket = socket
                    token = existing.token
                else:
                    token = secrets.token_hex(12)
                    s.participants[token] = Participant(token=token, name=name, socket=socket)
            # EVERY attach path ends with the participant on the scoreboard —
            # a reconnect after the board player was deleted via REST would
            # otherwise come back as a ghost (can buzz, can't be awarded).
            # Cache check first; store IO runs off-loop (lock stays held —
            # the point is buzz arbitration never stalls behind file IO).
            if not any(n == name for n, _ in s.scores):
                joined_name = name

                def ensure(board: Board) -> None:
                    # idempotent under the store lock; survives a lost race
                    if not any(p.name == joined_name for p in board.players):
                        board.players.append(Player(name=joined_name))

                try:
                    await asyncio.to_thread(store.update_board, s.board_id, ensure)
                except Exception:
                    pass  # board deleted mid-session — session still works
                s.scores, s.control = await asyncio.to_thread(
                    _read_board_view, s.board_id
                )
            await self._broadcast(exclude=socket)
            return token, s.snapshot()

    async def detach(self, socket: WebSocket) -> None:
        async with self._lock:
            s = self._session
            if s is None:
                return
            s.host_sockets.discard(socket)
            for p in s.participants.values():
                if p.socket is socket:
                    p.socket = None
            await self._broadcast()

    # ---------------------------------------------------------------- #
    #  Buzzer                                                          #
    # ---------------------------------------------------------------- #
    async def buzz(self, socket: WebSocket) -> None:
        async with self._lock:
            s = self._session
            if s is None:
                return
            player = next(
                (p for p in s.participants.values() if p.socket is socket), None
            )
            if player is None or player.name in s.locked_out:
                return
            now = time.monotonic()
            if not s.armed:
                # False start: each early press re-triggers the freeze, so a
                # masher stays frozen for as long as they keep mashing.
                player.frozen_until = now + FALSE_START_PENALTY
                return
            if now < player.frozen_until:
                player.frozen_until = now + FALSE_START_PENALTY
                return
            if s.armed and player.name not in s.order:
                s.order.append(player.name)
                if s.winner is None:
                    s.winner = player.name
                await self._broadcast()

    async def host_command(
        self, socket: WebSocket, command: str, target: str | None = None
    ) -> None:
        async with self._lock:
            s = self._session
            if s is None or socket not in s.host_sockets:
                return
            if command == "kick":
                # Host-authoritative removal: frees a zombie-claimed name
                # instantly (beats the ~40s WS heartbeat) and invalidates the
                # device's token so a revived zombie can't hijack the slot
                # back. Board player + score are untouched — rejoining lands
                # in the same scoreboard identity. Buzzer name-state (order/
                # lockouts) is left alone; the host can Reset if needed.
                p = next(
                    (p for p in s.participants.values() if p.name == target), None
                )
                if p is not None:
                    del s.participants[p.token]
                    if p.socket is not None:
                        try:
                            # 'error' is fatal client-side: no auto-reconnect.
                            await p.socket.send_json(
                                {"type": "error", "message": "Removed by the host"}
                            )
                            await p.socket.close()
                        except Exception:
                            pass  # zombie — its receive loop will clean up
                await self._broadcast()
                return
            if command == "arm":
                s.armed, s.winner, s.order = True, None, []
            elif command == "disarm":
                s.armed, s.winner, s.order = False, None, []
            elif command == "rearm-excluding-winner":
                if s.winner is not None:
                    s.locked_out.add(s.winner)
                s.armed, s.winner, s.order = True, None, []
            elif command == "reset-buzzer":
                s.armed, s.winner, s.order = False, None, []
                s.locked_out.clear()
            elif command == "end-session":
                await self._broadcast_raw({"type": "ended"})
                self._session = None
                return
            await self._broadcast()

    # ---------------------------------------------------------------- #
    #  Score sync (game endpoints → live clients)                      #
    # ---------------------------------------------------------------- #
    async def refresh_scores(
        self, board_id: str, player: str | None = None, delta: int | None = None
    ) -> None:
        """Reload the score cache and broadcast. With player+delta this is an
        award: clients get a transient 'result' (drives the phone ±$ flash)
        carrying the fresh snapshot; otherwise a plain snapshot broadcast."""
        async with self._lock:
            s = self._session
            if s is None or s.board_id != board_id:
                return
            s.scores, s.control = await asyncio.to_thread(_read_board_view, board_id)
            if player is not None and delta is not None:
                await self._broadcast_raw(
                    {
                        "type": "result",
                        "player": player,
                        "delta": delta,
                        "snapshot": s.snapshot(),
                    }
                )
            else:
                await self._broadcast()

    def notify_scores(
        self, board_id: str, player: str | None = None, delta: int | None = None
    ) -> None:
        """Threadsafe fire-and-forget for SYNC game endpoints (threadpool).
        Cheap no-op when no session is live — game routes never block on us."""
        loop = self._loop
        if loop is None or loop.is_closed() or self._session is None:
            return
        future = asyncio.run_coroutine_threadsafe(
            self.refresh_scores(board_id, player, delta), loop
        )
        future.add_done_callback(lambda f: f.exception())  # log-free swallow

    async def rename_participant(self, board_id: str, old: str, new: str) -> None:
        """A board player was renamed via REST: rewrite every name-keyed
        piece of session state (participant identity, winner, buzz order,
        lockouts) so a mid-'won' rename leaves the winner awardable, then
        refresh the score cache and broadcast."""
        async with self._lock:
            s = self._session
            if s is None or s.board_id != board_id:
                return
            for p in s.participants.values():
                if p.name == old:
                    p.name = new
            if s.winner == old:
                s.winner = new
            s.order = [new if n == old else n for n in s.order]
            if old in s.locked_out:
                s.locked_out.discard(old)
                s.locked_out.add(new)
            s.scores, s.control = await asyncio.to_thread(_read_board_view, board_id)
            await self._broadcast()

    def notify_rename(self, board_id: str, old: str, new: str) -> None:
        """Threadsafe fire-and-forget counterpart, for rename_player."""
        loop = self._loop
        if loop is None or loop.is_closed() or self._session is None:
            return
        future = asyncio.run_coroutine_threadsafe(
            self.rename_participant(board_id, old, new), loop
        )
        future.add_done_callback(lambda f: f.exception())  # log-free swallow

    def participant_names(self, board_id: str) -> set[str]:
        """Lock-free best-effort peek for SYNC routes (threadpool): the
        editor's full-doc save must not delete players who are live
        participants. No lock needed for correctness we can't have anyway —
        list() snapshots the dict atomically under the GIL, and a join that
        races the caller is self-healing (attach_player re-ensures its board
        player on every attach)."""
        s = self._session
        if s is None or s.board_id != board_id:
            return set()
        return {p.name for p in list(s.participants.values())}

    # ---------------------------------------------------------------- #
    #  Broadcast                                                       #
    # ---------------------------------------------------------------- #
    async def _broadcast(self, exclude: WebSocket | None = None) -> None:
        if self._session is not None:
            await self._broadcast_raw(
                {"type": "snapshot", "snapshot": self._session.snapshot()},
                exclude=exclude,
            )

    async def _broadcast_raw(
        self, message: dict[str, Any], exclude: WebSocket | None = None
    ) -> None:
        s = self._session
        if s is None:
            return
        sockets = [
            sock
            for sock in (
                list(s.host_sockets)
                + [p.socket for p in s.participants.values() if p.socket is not None]
            )
            if sock is not exclude
        ]
        results = await asyncio.gather(
            *(sock.send_json(message) for sock in sockets), return_exceptions=True
        )
        # Dead sockets are detached lazily on their own receive-loop exit.
        del results


manager = SessionManager()
