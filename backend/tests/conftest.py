"""Shared fixtures for the backend test suite.

The routers import the module-level singleton `store` from app.storage
(`from ..storage import store`), so test isolation works by MUTATING that
object to point at a per-test temp directory — re-assigning
app.storage.store would leave the routers holding the old instance.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `app` is not an installed package; make backend/ importable regardless of
# how pytest was invoked.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.storage import store  # noqa: E402

# Tiny fake media payloads — the backend keys off the file extension only.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-payload" * 4
MP3_BYTES = b"ID3" + b"fake-mp3-payload" * 4


@pytest.fixture(autouse=True)
def isolated_store(tmp_path):
    """Point the shared BoardStore singleton at a fresh temp directory."""
    old_data_dir = store.data_dir
    old_boards_dir = store.boards_dir
    store.data_dir = tmp_path / "data"
    store.boards_dir = store.data_dir / "boards"
    store.boards_dir.mkdir(parents=True, exist_ok=True)
    yield store
    store.data_dir = old_data_dir
    store.boards_dir = old_boards_dir


@pytest.fixture(autouse=True)
def isolated_session_manager():
    """Reset the SessionManager singleton between tests (same mutate-don't-
    reassign rule as the store above).

    Each TestClient runs its own event loop, but an asyncio.Lock binds to
    whichever loop first CONTENDS it — and the score-notify bridge makes
    contention routine. A lock bound in one test then raises "bound to a
    different event loop" in the next. A fresh Lock (and cleared session/loop
    refs) per test keeps every binding test-local. Production is unaffected:
    one process, one loop, forever.
    """
    import asyncio

    from app.session import manager

    manager._session = None
    manager._loop = None
    manager._lock = asyncio.Lock()
    yield manager
    manager._session = None
    manager._loop = None


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def board(client):
    """A freshly created default board, as the API returns it (dict)."""
    r = client.post("/api/boards", json={"name": "Test Board"})
    assert r.status_code == 201
    return r.json()


def upload_asset(client, board_id: str, filename: str, content: bytes):
    """POST an asset upload; returns the httpx Response."""
    return client.post(
        f"/api/boards/{board_id}/assets",
        files={"file": (filename, content, "application/octet-stream")},
    )
