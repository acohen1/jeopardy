"""FastAPI application entry point.

Dev:      uv run uvicorn app.main:app --reload --port 8000
          (the Vite dev server proxies /api → :8000)
Packaged: the Electron shell spawns this as a sidecar exe and points
          FRONTEND_DIST at the built frontend, which is then served
          directly — one process, one origin, no proxy.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .routers import assets, boards, game, live
from .storage import BoardNotFound

app = FastAPI(title="Chaewon Jeopardy", version="2.0.0")


@app.exception_handler(BoardNotFound)
def board_not_found_handler(request: Request, exc: BoardNotFound) -> JSONResponse:
    """A board deleted between a route's 404-check and a store call (or any
    store-level miss) is a 404, never a 500."""
    return JSONResponse(status_code=404, content={"detail": "Board not found"})

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(boards.router)
app.include_router(game.router)
app.include_router(assets.router)
app.include_router(live.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ------------------------------------------------------------------ #
#  Packaged mode: serve the built frontend (SPA) from this process    #
# ------------------------------------------------------------------ #
_frontend_dist = os.environ.get("FRONTEND_DIST", "")
if _frontend_dist and Path(_frontend_dist).is_dir():
    from fastapi.staticfiles import StaticFiles

    _dist = Path(_frontend_dist)
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="static")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        """Serve real files if they exist; everything else falls back to
        index.html so client-side routes (/boards/x/play) deep-link."""
        candidate = (_dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(_dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
