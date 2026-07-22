"""Play-time game state: players, scores, used cells, settings.

Server-authoritative and fine-grained so a future TV/audience view (or
WebSocket subscription) can layer on without reworking the API. Every
mutation returns the full updated Board — clients simply replace their
cached copy.

All mutations go through store.update_board, which holds the store lock
across the read-modify-write so concurrent updates never lose each other.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..models import Board, FirstPick, MultiAwardRule, Player, ScoreEvent, TurnMode
from ..session import manager
from ..storage import store
from .boards import get_or_404

router = APIRouter(prefix="/api/boards/{board_id}", tags=["game"])


class PlayerRequest(BaseModel):
    name: str


class AwardRequest(BaseModel):
    delta: int
    note: str = ""


class SetScoreRequest(BaseModel):
    score: int
    note: str = ""


class UsedRequest(BaseModel):
    used: bool


class SettingsRequest(BaseModel):
    # All optional: None = leave as-is, so a partial PUT (e.g. the negatives
    # toggle) can never silently reset the other rules to their defaults.
    allow_negatives: bool | None = None
    turn_mode: TurnMode | None = None
    multi_award: MultiAwardRule | None = None
    first_pick: FirstPick | None = None


class ControlRequest(BaseModel):
    player: str | None  # None = nobody has the board


def _clean_player_name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Player name cannot be empty")
    if "/" in name or "\\" in name:
        # names address /players/{name} routes — separators would break them
        raise HTTPException(
            status_code=422, detail="Player name cannot contain / or \\"
        )
    return name


def _find_player(board: Board, name: str) -> Player:
    for p in board.players:
        if p.name == name:
            return p
    raise HTTPException(status_code=404, detail=f"Player '{name}' not found")


@router.post("/players", status_code=201)
def add_player(board_id: str, req: PlayerRequest) -> Board:
    name = _clean_player_name(req.name)

    def mutate(board: Board) -> None:
        if any(p.name == name for p in board.players):
            raise HTTPException(
                status_code=409, detail=f"Player '{name}' already exists"
            )
        board.players.append(Player(name=name))

    get_or_404(board_id)
    board = store.update_board(board_id, mutate)
    manager.notify_scores(board_id)
    return board


@router.delete("/players/{name}")
def remove_player(board_id: str, name: str) -> Board:
    def mutate(board: Board) -> None:
        board.players = [p for p in board.players if p.name != name]

    get_or_404(board_id)
    board = store.update_board(board_id, mutate)
    manager.notify_scores(board_id)
    return board


@router.patch("/players/{name}")
def rename_player(board_id: str, name: str, req: PlayerRequest) -> Board:
    new_name = _clean_player_name(req.name)

    def mutate(board: Board) -> None:
        if new_name != name and any(p.name == new_name for p in board.players):
            raise HTTPException(
                status_code=409, detail=f"Player '{new_name}' already exists"
            )
        _find_player(board, name).name = new_name
        if board.control_player == name:
            board.control_player = new_name

    get_or_404(board_id)
    board = store.update_board(board_id, mutate)
    # Session state keys on names — a plain score refresh would leave the
    # participant/winner/order under the old name (winner unawardable).
    manager.notify_rename(board_id, name, new_name)
    return board


def _log(board: Board, event: ScoreEvent) -> None:
    board.history.append(event)  # normalize_board trims to MAX_HISTORY on write


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/players/{name}/award")
def award(board_id: str, name: str, req: AwardRequest) -> Board:
    def mutate(board: Board) -> None:
        p = _find_player(board, name)
        before = p.score
        p.score += req.delta
        _log(board, ScoreEvent(
            ts=_now_iso(), player=name, kind="award",
            delta=req.delta, before=before, after=p.score, note=req.note,
        ))

    get_or_404(board_id)
    board = store.update_board(board_id, mutate)
    # Awards flash on phones ('result'); everything else is a plain refresh.
    manager.notify_scores(board_id, player=name, delta=req.delta)
    return board


@router.put("/players/{name}/score")
def set_score(board_id: str, name: str, req: SetScoreRequest) -> Board:
    """Host correction: set a player's score to an absolute value (logged)."""
    def mutate(board: Board) -> None:
        p = _find_player(board, name)
        before = p.score
        p.score = req.score
        _log(board, ScoreEvent(
            ts=_now_iso(), player=name, kind="set",
            delta=req.score - before, before=before, after=p.score, note=req.note,
        ))

    get_or_404(board_id)
    board = store.update_board(board_id, mutate)
    manager.notify_scores(board_id)
    return board


@router.post("/history/undo")
def undo_score(board_id: str) -> Board:
    """Reverse the most recent scoring action (award, deduct, or manual set)."""
    def mutate(board: Board) -> None:
        if not board.history:
            raise HTTPException(status_code=409, detail="Nothing to undo")
        event = board.history.pop()
        for p in board.players:
            if p.name == event.player:
                p.score = event.before
                break
        # player renamed/removed since: the event is still popped

    get_or_404(board_id)
    board = store.update_board(board_id, mutate)
    manager.notify_scores(board_id)
    return board


@router.post("/scores/reset")
def reset_scores(board_id: str) -> Board:
    def mutate(board: Board) -> None:
        for p in board.players:
            p.score = 0
        board.history = []  # a fresh game starts a fresh log
        board.control_player = None  # fresh game re-picks who starts

    get_or_404(board_id)
    board = store.update_board(board_id, mutate)
    manager.notify_scores(board_id)
    return board


@router.put("/cells/{row}/{col}/used")
def set_cell_used(board_id: str, row: int, col: int, req: UsedRequest) -> Board:
    def mutate(board: Board) -> None:
        # bounds-check against the actual array, not just the declared dims
        if not (0 <= row < len(board.cells) and 0 <= col < len(board.cells[row])):
            raise HTTPException(status_code=404, detail="Cell out of range")
        board.cells[row][col].used = req.used

    get_or_404(board_id)
    return store.update_board(board_id, mutate)


@router.post("/cells/reset-used")
def reset_used(board_id: str) -> Board:
    def mutate(board: Board) -> None:
        for row in board.cells:
            for cell in row:
                cell.used = False

    get_or_404(board_id)
    return store.update_board(board_id, mutate)


@router.put("/settings")
def update_settings(board_id: str, req: SettingsRequest) -> Board:
    changed = req.model_dump(exclude_none=True)

    def mutate(board: Board) -> None:
        for key, value in changed.items():
            setattr(board, key, value)

    get_or_404(board_id)
    board = store.update_board(board_id, mutate)
    # The host's latest rule choices become the defaults for future boards.
    store.set_app_defaults(changed)
    manager.notify_scores(board_id)
    return board


@router.put("/control")
def set_control(board_id: str, req: ControlRequest) -> Board:
    """Hand board control to a player (or nobody). The frontend drives the
    turn-mode transitions (it owns the clue lifecycle); this endpoint keeps
    the STATE server-authoritative: validated, persisted, broadcast live."""
    def mutate(board: Board) -> None:
        if req.player is not None:
            _find_player(board, req.player)  # 404 on unknown names
        board.control_player = req.player

    get_or_404(board_id)
    board = store.update_board(board_id, mutate)
    manager.notify_scores(board_id)
    return board