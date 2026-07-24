---
name: verify
description: Build, run, and drive the Rhubarb web app (FastAPI backend + Vite frontend) for end-to-end verification with Playwright.
---

# Verifying Rhubarb

## Toolchain paths (NOT on default PATH in non-interactive shells)

- Node 22 (fnm): `C:\Users\alexc\AppData\Roaming\fnm\node-versions\v22.22.3\installation`
- uv: `C:\Users\alexc\.local\bin`

Prefix `$env:PATH` with these in every PowerShell command.

## Launch

```powershell
# backend (from backend/): uv run uvicorn app.main:app --port 8000
# frontend (from frontend/): npm run dev        → http://localhost:5173 (proxies /api → :8000)
# or both from repo root: npm run dev
```

Health check: `http://127.0.0.1:8000/api/health` (use 127.0.0.1 — PowerShell's
`localhost` may resolve to ::1 and false-negative; the app itself is fine).

## Static checks (CI-tier, not verification)

- Frontend: `npx tsc --noEmit` and `npx vite build` (in frontend/)
- Backend: `uv run pytest -q` (in backend/, 50+ tests)

## Seed a rich test board

A seeding script pattern lives in the session scratchpad as `seed_board.py`:
creates a board via the API, uploads real media from `legacy/assets/`
(webm video, mp3 ×2 for stacked audio, .mov, PNGs, a generated GIF), builds
cells covering text-only / single-media / stacked-audio / 2-3-4-item collages,
and adds players. Run with `uv run --with pillow --with httpx python seed_board.py`.

## Drive (Playwright)

Install Playwright + Chromium in a scratch dir (NOT the repo):
`npm i playwright && npx playwright install chromium`.

Selector gotchas learned the hard way:
- Toasts/text: always use `.first()` or `{ exact: true }` — bare `getByText`
  substring-matches every ancestor div (strict-mode violations cascade).
- Board cells: buttons with exact money text (`$200`); all cells in a row share
  the text — index with `.nth(col)`. Used cells keep their money text.
- The library list is sorted **newest-first**: after an import, `.first()` of a
  duplicated name is the imported copy.
- Award/deduct buttons: `+ Name` / `− Name`; award rows render before deduct.
- Toast texts: `+ $200 → Alex` / `− $600 → Chaewon`.
- Reset buttons are text-named (`Reset scores`, `Reset board`) — the
  `title="Reset …"` strings in PlayMode are ConfirmDialog title PROPS, not
  HTML title attributes.
- A failed step often leaves the clue overlay open and every later cell click
  times out behind it — press Escape + assert `video` count 0 between flows.

## Key behavioral invariants to spot-check

- Nothing auto-plays, ever (assert `video.paused` after opening a clue).
- Opening an unused cell marks it used immediately; used cells are inert to
  left-click, right-click → Review / Reset cell.
- Question-page award: toast + overlay stays; answer-page award: closes.
- Hotkeys: Space/←→/R/F route to most-recently-clicked timed cell; A/Q/Esc
  drive the overlay pages.
- Stacked audio: one transport, all `<audio>` elements play aligned at their
  stored per-clip volumes.
