"""Board library CRUD + import/export."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from ..models import Board, BoardSummary
from ..storage import BoardNotFound, store

router = APIRouter(prefix="/api/boards", tags=["boards"])


class CreateBoardRequest(BaseModel):
    name: str = "Untitled Board"


class RenameBoardRequest(BaseModel):
    name: str


def get_or_404(board_id: str) -> Board:
    try:
        return store.get_board(board_id)
    except BoardNotFound:
        raise HTTPException(status_code=404, detail="Board not found")


@router.get("")
def list_boards() -> list[BoardSummary]:
    return store.list_boards()


@router.get("/storage/orphans")
def orphan_report() -> dict:
    """Unreferenced media old enough to delete safely (count + bytes)."""
    return store.orphan_report()


@router.post("/storage/tidy")
def tidy_media() -> dict:
    """Delete orphaned media; returns {files, bytes} freed."""
    return store.tidy_media()


@router.post("", status_code=201)
def create_board(req: CreateBoardRequest) -> Board:
    return store.create_board(req.name)


@router.post("/import", status_code=201)
async def import_board(file: UploadFile) -> Board:
    content = await file.read()
    try:
        return store.import_package(file.filename or "Imported Board", content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{board_id}")
def get_board(board_id: str) -> Board:
    return get_or_404(board_id)


@router.put("/{board_id}")
def save_board(board_id: str, board: Board) -> Board:
    """Full-document CONTENT save (the editor's autosave).

    The editor owns content; play-time state is owned by the fine-grained
    game endpoints. To keep a stale editor snapshot from silently reverting
    a concurrent award or used-cell change, game-state fields are re-read
    from the server copy: scores merge by player name, used flags by cell
    position. Everything else comes from the payload.
    """
    current = get_or_404(board_id)
    board.id = board_id  # path wins over payload

    server_scores = {p.name: p.score for p in current.players}
    for p in board.players:
        if p.name in server_scores:
            p.score = server_scores[p.name]
    for r, row in enumerate(board.cells):
        for c, cell in enumerate(row):
            if r < len(current.cells) and c < len(current.cells[r]):
                cell.used = current.cells[r][c].used
    board.history = current.history  # score log is game state, never editor's

    return store.save_board(board)


@router.patch("/{board_id}")
def rename_board(board_id: str, req: RenameBoardRequest) -> Board:
    board = get_or_404(board_id)
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    board.name = name
    return store.save_board(board)


@router.delete("/{board_id}", status_code=204)
def delete_board(board_id: str) -> None:
    try:
        store.delete_board(board_id)
    except BoardNotFound:
        raise HTTPException(status_code=404, detail="Board not found")


@router.post("/{board_id}/duplicate", status_code=201)
def duplicate_board(board_id: str) -> Board:
    get_or_404(board_id)
    return store.duplicate_board(board_id)


@router.get("/{board_id}/export")
def export_board(board_id: str) -> Response:
    board = get_or_404(board_id)
    data = store.export_zip(board_id)
    # .jeopardy (a zip inside) — a single custom extension so the desktop
    # app can own the file association without hijacking .zip
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", board.name).strip("_") or "board"
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}.jeopardy"'
        },
    )
