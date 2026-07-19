# Chaewon Jeopardy

A custom Jeopardy game builder + player. Vite/React/TypeScript frontend (TanStack Router + Query, Tailwind v4), FastAPI backend.

The original PyQt6 desktop app lives in [`legacy/`](legacy/) and remains runnable (see its README).

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Vite, React 19, TypeScript, TanStack Router (file-based), TanStack Query, Tailwind CSS v4 |
| Backend | FastAPI + uvicorn (Python 3.13, managed with `uv`) |
| Storage | File-based board library under `backend/data/` (swappable for a DB later) |
| Media | Native `<video>`/`<audio>` with custom transports; stacked audio via Web Audio API (no ffmpeg) |

## Development

```sh
# one-time setup
cd backend && uv sync && cd ..
cd frontend && npm install && cd ..
npm install            # root: concurrently

# run both servers
npm run dev            # backend :8000, frontend :5173 (proxies /api)
```

Open http://localhost:5173.

## Layout

```
backend/
  app/
    main.py        # FastAPI app
    models.py      # Pydantic domain models + legacy-format migration
    storage.py     # file-based board store (boards/<id>/board.json + assets/)
    routers/       # boards, game-state, assets endpoints
  tests/
frontend/
  src/
    routes/        # TanStack file-based routes: library, edit, play
    components/    # ui/ (primitives), slides/, editor/, play/, library/
    hooks/         # useHotkeys, useStackedAudio, ...
    api/           # typed client + query/mutation helpers
    types/         # domain types (mirror backend models)
    lib/           # media type map, formatters
legacy/            # original PyQt6 app (frozen)
```

## Hotkeys

Press <kbd>?</kbd> (<kbd>Shift</kbd>+<kbd>/</kbd> on US layouts) anywhere in the app — or the keyboard button, bottom-right — for the full in-app reference. Highlights: clue overlay <kbd>A</kbd>/<kbd>Q</kbd>/<kbd>T</kbd>/<kbd>Esc</kbd>, media <kbd>Space</kbd>/<kbd>←</kbd><kbd>→</kbd>/<kbd>R</kbd>/<kbd>F</kbd>, play <kbd>P</kbd> (present mode), editor <kbd>Ctrl+S</kbd>. All bare-key shortcuts pause while typing or while a dialog is open, so they never fight the browser or OS.

## Boards & media

- Boards live in a library (create / rename / duplicate / delete from the home page).
- Export any board as a portable `.zip` save package (board.json + assets); import accepts those zips **and** bare `.json` saves from the legacy desktop app.
- Media per slide: up to 4 items, any mix of image / GIF / video / audio. Nothing ever auto-plays.
