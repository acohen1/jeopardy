/** PlayMode — the gameplay screen: top bar, board grid, scoreboard, clue
 * overlay. Server-authoritative: renders from the board query; every game
 * mutation goes through useGameActions and the cache syncs from the response.
 * Legacy parity (play_mode.py PlayMode):
 *  - opening an UNUSED cell marks it used IMMEDIATELY (not on award);
 *  - used cells are inert except right-click → Review / Reset cell;
 *  - Review opens the overlay at the question page without touching `used`. */
import { useSuspenseQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { clsx } from 'clsx'
import { ArrowLeft, Flag, Minimize2, Presentation, RotateCcw, Volume2, VolumeX } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'

import { boardQuery, useGameActions } from '@/api/boards'
import { useHotkeys } from '@/hooks/useHotkeys'
import { usePageTitle } from '@/hooks/usePageTitle'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ContextMenu, type ContextMenuState } from '@/components/ui/ContextMenu'
import { toast } from '@/components/ui/Toaster'
import { money, truncate } from '@/lib/format'
import { isMuted, playSfx, useSfxMuted } from '@/lib/sfx'
import { cellIsFilled, type Cell } from '@/types/board'

import { BoardGrid } from './BoardGrid'
import { ClueOverlay } from './ClueOverlay'
import { PodiumOverlay } from './PodiumOverlay'
import { Scoreboard } from './Scoreboard'

interface OverlayState {
  row: number
  col: number
  /** Snapshot taken at open — keeps slide identity stable while media plays. */
  cell: Cell
}

export function PlayMode({ boardId }: { boardId: string }) {
  const { data: board } = useSuspenseQuery(boardQuery(boardId))
  const actions = useGameActions(boardId)
  usePageTitle(`${board.name} · Play — Chaewon Jeopardy`)

  const [overlay, setOverlay] = useState<OverlayState | null>(null)
  const [menu, setMenu] = useState<ContextMenuState | null>(null)
  const [confirmBoardReset, setConfirmBoardReset] = useState(false)
  const [confirmScoreReset, setConfirmScoreReset] = useState(false)
  const [presenting, setPresenting] = useState(false)
  const [podium, setPodium] = useState(false)
  const [sfxMuted, toggleSfxMuted] = useSfxMuted()

  // Present mode is fullscreen-backed: whatever way fullscreen ends (native
  // Esc, our exit button, 'P') the chrome comes back via this listener.
  useEffect(() => {
    const sync = () => setPresenting(document.fullscreenElement != null)
    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])

  const togglePresent = () => {
    if (document.fullscreenElement) {
      void document.exitFullscreen().catch(() => undefined)
    } else {
      void document.documentElement.requestFullscreen().catch(() => undefined)
    }
  }

  // 'P' toggles present mode only while the clue overlay is closed.
  useHotkeys({ p: togglePresent }, { enabled: overlay === null })

  // 'M' toggles sounds ALWAYS on the play page — no other binding uses it,
  // and it must reach the host even mid-clue or over a confirm dialog.
  const toggleSounds = () => {
    toggleSfxMuted()
    toast(isMuted() ? 'Sounds off' : 'Sounds on')
  }
  useHotkeys({ m: toggleSounds }, { allowInModals: true })

  const openOverlay = (row: number, col: number) => {
    const cell = board.cells[row]?.[col]
    if (cell) setOverlay({ row, col, cell })
  }

  const onOpenCell = (row: number, col: number) => {
    // Legacy parity: the cell is marked used the moment it opens, not on award.
    playSfx('pick')
    openOverlay(row, col)
    actions.setCellUsed.mutate([row, col, true])
  }

  // One-time nudge (per mount): every filled clue has been played and nothing
  // is on screen — suggest the podium.
  const suggestedFinishRef = useRef(false)
  useEffect(() => {
    if (suggestedFinishRef.current || overlay !== null || podium) return
    const filled = board.cells.flat().filter(cellIsFilled)
    if (filled.length > 0 && filled.every((c) => c.used)) {
      suggestedFinishRef.current = true
      toast('All clues played — hit Finish for the podium 🏆', { duration: 4000 })
    }
  }, [board, overlay, podium])

  const onUsedCellMenu = (e: ReactMouseEvent, row: number, col: number) => {
    setMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { label: 'Review', onSelect: () => openOverlay(row, col) },
        { type: 'separator' },
        { label: 'Reset cell', onSelect: () => actions.setCellUsed.mutate([row, col, false]) },
      ],
    })
  }

  return (
    <main className="flex h-dvh flex-col overflow-hidden">
      {/* ---- Top bar ---- */}
      <header className="grid shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-4 px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          {!presenting && (
            <>
              <Link
                to="/boards/$boardId/edit"
                params={{ boardId }}
                className="text-ink-muted border-line/60 hover:bg-surface hover:text-ink hover:border-line inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-1.5 text-sm transition-colors duration-100"
              >
                <ArrowLeft className="size-4" />
                Edit board
              </Link>
              <Button variant="danger" onClick={() => setConfirmBoardReset(true)}>
                <RotateCcw className="size-4" />
                Reset board
              </Button>
              <NegativesToggle
                checked={board.allow_negatives}
                onChange={(v) => actions.setAllowNegatives.mutate([v])}
              />
            </>
          )}
        </div>
        <div className="text-center">
          <h1 className="font-display text-accent text-2xl font-bold tracking-[0.3em]">
            JEOPARDY!
          </h1>
          <p className="text-ink-muted mt-0.5 text-xs">{board.name}</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {!presenting && (
            <>
              <Button variant="ghost" onClick={toggleSounds} title="Sounds [M]">
                {sfxMuted ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
              </Button>
              <Button
                variant="soft"
                onClick={() => setPodium(true)}
                title="Finish game — show the podium"
              >
                <Flag className="size-4" />
                Finish
              </Button>
              <Button variant="soft" onClick={togglePresent} title="Present mode [P]">
                <Presentation className="size-4" />
                Present
              </Button>
            </>
          )}
        </div>
      </header>

      {/* Low-key exit affordance while presenting */}
      {presenting && (
        <button
          type="button"
          onClick={togglePresent}
          title="Exit present mode [P]"
          className="text-ink-muted hover:text-ink fixed top-2 left-2 z-30 cursor-pointer rounded-lg p-2 opacity-40 transition-opacity duration-150 hover:opacity-100"
        >
          <Minimize2 className="size-4" />
        </button>
      )}

      {/* ---- Board + scoreboard ---- */}
      <div className="flex min-h-0 flex-1 gap-3 px-3 pb-3">
        <BoardGrid board={board} onOpenCell={onOpenCell} onUsedCellMenu={onUsedCellMenu} />
        <Scoreboard
          players={board.players}
          history={board.history}
          onResetScores={() => setConfirmScoreReset(true)}
          onSetScore={(name, score) => actions.setScore.mutate([name, score, 'manual edit'])}
          onUndo={() => actions.undoScore.mutate([])}
        />
      </div>

      {/* ---- Clue overlay (unmount on close stops all media) ---- */}
      {overlay && (
        <ClueOverlay
          boardId={boardId}
          cell={overlay.cell}
          players={board.players}
          allowNegatives={board.allow_negatives}
          onAward={(name, delta) => {
            // History-feed note: "Category 3 · $600" (deducts share the note);
            // bonus opens carry the wager-based delta and a "★ " prefix, e.g.
            // "★ Category 3 · $1,200".
            const catName =
              board.categories[overlay.col]?.trim() || `Category ${overlay.col + 1}`
            const isBonusOpen = overlay.cell.bonus && !overlay.cell.used
            const note = `${isBonusOpen ? '★ ' : ''}${truncate(catName, 24)} · ${money(Math.abs(delta))}`
            actions.award.mutate([name, delta, note])
          }}
          onClose={() => setOverlay(null)}
        />
      )}

      {/* ---- Podium (works during present mode — it's FOR the TV) ---- */}
      {podium && (
        <PodiumOverlay
          players={board.players}
          onPlayAgain={() => {
            actions.resetScores.mutate([])
            actions.resetUsed.mutate([])
          }}
          onClose={() => setPodium(false)}
        />
      )}

      <ContextMenu state={menu} onClose={() => setMenu(null)} />

      <ConfirmDialog
        open={confirmBoardReset}
        title="Reset board"
        message="Mark all cells as unused?"
        confirmLabel="Reset"
        danger
        onConfirm={() => {
          actions.resetUsed.mutate([])
          setConfirmBoardReset(false)
        }}
        onCancel={() => setConfirmBoardReset(false)}
      />
      <ConfirmDialog
        open={confirmScoreReset}
        title="Reset scores"
        message="Reset all player scores to 0?"
        confirmLabel="Reset"
        danger
        onConfirm={() => {
          actions.resetScores.mutate([])
          setConfirmScoreReset(false)
        }}
        onCancel={() => setConfirmScoreReset(false)}
      />
    </main>
  )
}

function NegativesToggle({
  checked,
  onChange,
}: {
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="group flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5"
    >
      <span
        className={clsx(
          'relative h-4.5 w-8 shrink-0 rounded-full transition-colors duration-150',
          checked ? 'bg-accent-deep' : 'bg-cell',
        )}
      >
        <span
          className={clsx(
            'bg-ink absolute top-0.5 left-0.5 size-3.5 rounded-full transition-transform duration-150',
            checked && 'translate-x-3.5',
          )}
        />
      </span>
      <span className="text-ink-muted group-hover:text-ink text-sm transition-colors duration-100">
        Allow negative scores
      </span>
    </button>
  )
}
