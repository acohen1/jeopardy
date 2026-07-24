# Rhubarb!

A party game-show builder + player: make a board of clue tiles, put it on the TV, and your friends' phones become the buzzers — on your wifi or across the internet. Vite/React/TypeScript frontend (TanStack Router + Query, Tailwind v4), FastAPI backend, shipped as a self-updating Electron desktop app.

> Formerly known as "Chaewon Jeopardy." The original PyQt6 desktop app lives in [`legacy/`](legacy/) and remains runnable (see its README).

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Vite, React 19, TypeScript, TanStack Router (file-based), TanStack Query, Tailwind CSS v4 |
| Backend | FastAPI + uvicorn (Python 3.13, managed with `uv`) |
| Desktop | Electron shell + PyInstaller sidecar, auto-updates via GitHub Releases |
| Live play | WebSocket sessions: room codes, QR joins, first-buzz-wins arbitration, turn order |
| Remote play | Bundled Cloudflare quick tunnel — friends join from anywhere, no hosting |
| Storage | File-based board library (swappable for a DB later) |
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

Open http://localhost:5173. Phones on your wifi can join games at the LAN URL shown in the lobby (Vite binds your network interface in dev).

## Layout

```
backend/
  app/
    main.py        # FastAPI app
    models.py      # Pydantic domain models + legacy-format migration
    storage.py     # file-based board store (boards/<id>/board.json + assets/)
    session.py     # live game sessions: room codes, buzzers, board control
    routers/       # boards, game-state, assets, live endpoints
  tests/
frontend/
  src/
    routes/        # TanStack file-based routes: library, edit, play, join
    components/    # ui/, slides/, editor/, play/, controller/, library/
    hooks/         # useHotkeys, useStackedAudio, ...
    api/           # typed client + query/mutation helpers
    lib/           # live-session protocol, desktop bridge, sfx, formatters
desktop/           # Electron shell, installer config, update machinery
legacy/            # original PyQt6 app (frozen)
```

## Hotkeys

Press <kbd>?</kbd> (<kbd>Shift</kbd>+<kbd>/</kbd> on US layouts) anywhere in the app — or the keyboard button, bottom-right — for the full in-app reference. Highlights: clue overlay <kbd>A</kbd>/<kbd>Q</kbd>/<kbd>T</kbd>/<kbd>Esc</kbd>, buzzer resolution <kbd>B</kbd>/<kbd>C</kbd>/<kbd>W</kbd>, media <kbd>Space</kbd>/<kbd>←</kbd><kbd>→</kbd>/<kbd>R</kbd>/<kbd>F</kbd>, play <kbd>P</kbd> (present mode), editor <kbd>Ctrl+S</kbd>. All bare-key shortcuts pause while typing or while a dialog is open, so they never fight the browser or OS.

## Boards & media

- Boards live in a library (create / rename / duplicate / delete from the home page).
- Export any board as a portable `.rhubarb` save package (board.json + assets); import accepts those, legacy `.jeopardy` packages, plain `.zip`, **and** bare `.json` saves from the original desktop app.
- Media per slide: up to 4 items, any mix of image / GIF / video / audio. Nothing ever auto-plays.

## Live play

Host a game from the lobby: friends scan the QR (wifi) or hit "Invite over the internet" for a public link. Phones and laptops become buzzers — first buzz wins, false starts get frozen, turn order follows your chosen rules (Rules button in the editor or play top bar), and Daily-Double-style ★ bonus tiles wager against the real cap.
