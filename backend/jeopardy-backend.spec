# PyInstaller spec — one-file backend sidecar for the desktop app.
# Build:  uv run pyinstaller jeopardy-backend.spec  (from backend/)
# Output: backend/dist/jeopardy-backend.exe
a = Analysis(
    ["desktop_entry.py"],
    pathex=["."],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    excludes=["pytest", "httpx"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="jeopardy-backend",
    console=False,
    upx=False,
)
