"""Sidecar entry point for the packaged desktop app.

The Electron shell spawns this (PyInstaller one-file exe) with:
  PORT           — the port to bind (shell picks a free one)
  RHUBARB_HOST  — 127.0.0.1 by default; 0.0.0.0 enables the LAN/TV view
  RHUBARB_DATA_DIR — %APPDATA%/Rhubarb
  FRONTEND_DIST  — path to the built frontend, served by FastAPI
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _wire_streams() -> None:
    """In a windowed (console=False) PyInstaller app, sys.stdout/stderr are
    None — uvicorn's logging would die on them. Point both at a log file in
    the data dir, which doubles as the app's diagnosable backend log."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_dir = Path(os.environ.get("RHUBARB_DATA_DIR", Path.home() / ".rhubarb"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "backend.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def main() -> None:
    _wire_streams()
    import uvicorn

    from app.main import app

    uvicorn.run(
        app,
        host=os.environ.get("RHUBARB_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8477")),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
