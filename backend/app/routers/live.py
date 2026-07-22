"""Live-session endpoints: create/end/inspect the session + the WebSocket.

Protocol (JSON over WS) — first client message declares the role:
  {type: 'hello-host',   hostKey}                     → host stream
  {type: 'hello-player', code, name, token?}          → player stream
then:
  player → {type: 'buzz'}
  host   → {type: 'command', command: 'arm' | 'disarm' |
            'rearm-excluding-winner' | 'reset-buzzer' | 'end-session'
            | 'kick', target?: name}   (kick removes a participant: slot +
            token gone, socket told "Removed by the host"; scores untouched)
server → {type: 'welcome', token?, snapshot} (always first) | {type: 'snapshot', snapshot}
       | {type: 'result', player, delta, snapshot}   (an award happened — flash it)
       | {type: 'error', message} | {type: 'ended'}

Snapshots carry `scoreboard`: every board player with score + phone presence.
Joining auto-creates (or case-insensitively adopts) a scoreboard player, so
participants ARE players and buzz winners are awardable by exact name.
"""
from __future__ import annotations

import socket as socketlib

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..session import manager
from .boards import get_or_404

router = APIRouter(prefix="/api", tags=["live"])


class CreateSessionRequest(BaseModel):
    board_id: str


def _lan_ips() -> list[str]:
    """Best-effort local IPs a phone on the wifi could reach.

    The UDP-connect trick learns the outbound interface without sending
    packets; getaddrinfo fills in the rest. Localhost is excluded."""
    ips: list[str] = []
    try:
        with socketlib.socket(socketlib.AF_INET, socketlib.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socketlib.getaddrinfo(socketlib.gethostname(), None):
            addr = info[4][0]
            if "." in addr and not addr.startswith("127.") and addr not in ips:
                ips.append(addr)
    except OSError:
        pass
    return ips


@router.post("/session")
async def create_session(req: CreateSessionRequest) -> dict:
    get_or_404(req.board_id)
    created = await manager.create(req.board_id)
    created["lanIps"] = _lan_ips()
    return created


@router.get("/session")
async def session_state() -> dict:
    snapshot = await manager.peek()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No active session")
    return snapshot


@router.get("/session/roster")
async def session_roster(code: str) -> list[dict]:
    """Pre-join "who are you?" lookup — anyone with the room code may ask."""
    roster = await manager.roster(code)
    if roster is None:
        raise HTTPException(status_code=404, detail="No session with that code")
    return roster


@router.delete("/session", status_code=204)
async def end_session() -> None:
    await manager.end()


@router.websocket("/ws")
async def websocket_endpoint(socket: WebSocket) -> None:
    await socket.accept()
    try:
        hello = await socket.receive_json()
    except (WebSocketDisconnect, Exception):
        return

    kind = hello.get("type")
    if kind == "hello-host":
        snapshot = await manager.attach_host(socket, str(hello.get("hostKey", "")))
        if snapshot is None:
            await socket.send_json({"type": "error", "message": "Bad host key or no session"})
            await socket.close()
            return
        await socket.send_json({"type": "welcome", "snapshot": snapshot})
    elif kind == "hello-player":
        joined = await manager.attach_player(
            socket,
            str(hello.get("code", "")),
            str(hello.get("name", "")),
            hello.get("token") or None,
        )
        if joined is None:
            await socket.send_json(
                {"type": "error", "message": "Wrong code, or that name is taken"}
            )
            await socket.close()
            return
        token, snapshot = joined
        await socket.send_json({"type": "welcome", "token": token, "snapshot": snapshot})
    else:
        await socket.close()
        return

    try:
        while True:
            message = await socket.receive_json()
            mtype = message.get("type")
            if mtype == "buzz":
                await manager.buzz(socket)
            elif mtype == "command":
                target = message.get("target")
                await manager.host_command(
                    socket,
                    str(message.get("command", "")),
                    target if isinstance(target, str) else None,
                )
            # unknown types are ignored (forward-compatible)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        await manager.detach(socket)
