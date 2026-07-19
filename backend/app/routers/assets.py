"""Asset upload + serving (with HTTP Range support for media seeking)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..storage import store
from .boards import get_or_404

router = APIRouter(prefix="/api/boards/{board_id}/assets", tags=["assets"])


class AssetUploadResponse(BaseModel):
    path: str
    asset_type: str


@router.post("", status_code=201)
async def upload_asset(board_id: str, file: UploadFile) -> AssetUploadResponse:
    get_or_404(board_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file")
    try:
        stored, asset_type = store.add_asset(
            board_id, file.filename or "pasted_image.png", content
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return AssetUploadResponse(path=stored, asset_type=asset_type)


@router.get("/{filename}")
def get_asset(board_id: str, filename: str) -> FileResponse:
    # Existence check only — parsing the whole board.json per request would
    # tax every HTTP Range chunk while a video is being scrubbed.
    if not store.board_exists(board_id):
        raise HTTPException(status_code=404, detail="Board not found")
    try:
        p = store.asset_path(board_id, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    # FileResponse (Starlette) honours Range requests — required for
    # <video>/<audio> seeking.
    return FileResponse(p)
