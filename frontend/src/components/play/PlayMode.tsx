/** PlayMode — the gameplay screen: top bar, board grid, scoreboard, clue
 * overlay. Server-authoritative: renders from the board query; every game
 * mutation goes through useGameActions and the cache syncs from the response.
 * Legacy parity (play_mode.py PlayMode):
 *  - opening an UNUSED cell marks it used IMMEDIATELY (not on award);
 *  - used cells are inert except right-click → Review / Reset cell;
 *  - Review opens the overlay at the question page without touching `used`. */
import { useQueryClient, useSuspenseQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { clsx } from 'clsx'
import {
  ArrowLeft,
  Flag,
  ListOrdered,
  Minimize2,
  Presentation,
  RotateCcw,
  Users,
  Volume2,
  VolumeX,
  Wifi,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'

import { boardQuery, useGameActions } from '@/api/boards'
import { api } from '@/api/client'
import { useHotkeys } from '@/hooks/useHotkeys'
import { usePageTitle } from '@/hooks/usePageTitle'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ContextMenu, type ContextMenuState } from '@/components/ui/ContextMenu'
import { toast } from '@/components/ui/Toaster'
import { desktop } from '@/lib/desktop'
import { createSession, endSession, useHostSocket, type SessionCreated } from '@/lib/live'
import { money, truncate } from '@/lib/format'
import { isMuted, playSfx, useSfxMuted } from '@/lib/sfx'
import { cellIsFilled, type Cell } from '@/types/board'

import { BoardGrid } from './BoardGrid'
import { ClueOverlay } from './ClueOverlay'
import { JoinPanel } from './JoinPanel'
import { LobbyScreen } from './LobbyScreen'
import { PodiumOverlay } from './PodiumOverlay'
import { RulesDialog } from './RulesDialog'
import { Scoreboard } from './Scoreboard'

interface OverlayState {
  row: number
  col: number
  /** Snapshot taken at open — keeps slide identity stable while media plays. */
  cell: Cell
  /** True for a fresh play (marked used at open); false for a Review.
   * Sequential turn mode only advances on fresh plays. */
  fresh: boolean
}

export function PlayMode({ boardId }: { boardId: string }) {
  const { data: board } = useSuspenseQuery(boardQuery(boardId))
  const actions = useGameActions(boardId)
  usePageTitle(`${board.name} · Play — Rhubarb`)

  // Lobby phase (edit → LOBBY → board): shown while the game is VIRGIN —
  // nothing played, nothing scored. Refreshing mid-game skips it; "Play
  // again" resets everything and cycles back to it.
  const [inLobby, setInLobby] = useState(
    () => board.history.length === 0 && !board.cells.some((row) => row.some((c) => c.used)),
  )
  const [overlay, setOverlay] = useState<OverlayState | null>(null)
  const [menu, setMenu] = useState<ContextMenuState | null>(null)
  const [confirmNewGame, setConfirmNewGame] = useState(false)
  const [confirmScoreReset, setConfirmScoreReset] = useState(false)
  const [rulesOpen, setRulesOpen] = useState(false)
  const [presenting, setPresenting] = useState(false)
  const [podium, setPodium] = useState(false)
  const [sfxMuted, toggleSfxMuted] = useSfxMuted()

  // ---- Live session (Jackbox-style phone buzzers over LAN) ----
  const [session, setSession] = useState<SessionCreated | null>(null)
  // Per-tab memory of the room this board is hosting (see rehydrate below).
  const sessionStoreKey = `live-host:${boardId}`
  const [joinOpen, setJoinOpen] = useState(false)
  const [lanPrompt, setLanPrompt] = useState(false)
  const [creating, setCreating] = useState(false)
  const live = useHostSocket(session?.hostKey ?? null)

  // Server says the session is gone (ended elsewhere / expired) → clear out.
  useEffect(() => {
    if (!live.ended) return
    setSession(null)
    setJoinOpen(false)
    sessionStorage.removeItem(sessionStoreKey)
    toast('Live session ended')
  }, [live.ended, sessionStoreKey])

  // The host key only exists at create time — remember it for THIS tab so an
  // edit-board round trip (common now that the lobby links there) reattaches
  // to the running room instead of silently abandoning it.
  useEffect(() => {
    if (session) return
    const raw = sessionStorage.getItem(sessionStoreKey)
    if (!raw) return
    let stored: SessionCreated
    try {
      stored = JSON.parse(raw) as SessionCreated
    } catch {
      sessionStorage.removeItem(sessionStoreKey)
      return
    }
    api
      .get<{ code: string; boardId: string }>('/api/session')
      .then((live) => {
        if (live.code === stored.code && live.boardId === boardId) setSession(stored)
        else sessionStorage.removeItem(sessionStoreKey)
      })
      .catch(() => sessionStorage.removeItem(sessionStoreKey)) // no session server-side
    // eslint intentionally quiet: run once per mount
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const hostGame = async (openPanel = true) => {
    if (session) {
      if (openPanel) setJoinOpen(true)
      return
    }
    if (creating) return
    // Desktop shell: hosting needs LAN access ON so phones can reach us.
    // Browser dev has no bridge — skip the check entirely.
    if (desktop) {
      try {
        const { enabled } = await desktop.lan.get()
        if (!enabled) {
          setLanPrompt(true)
          return
        }
      } catch {
        // Bridge hiccup — fall through and let createSession speak for itself.
      }
    }
    setCreating(true)
    try {
      const created = await createSession(board.id)
      setSession(created)
      sessionStorage.setItem(sessionStoreKey, JSON.stringify(created))
      if (openPanel) setJoinOpen(true)
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Could not start a session', { kind: 'error' })
    } finally {
      setCreating(false)
    }
  }

  const endLiveSession = () => {
    setSession(null)
    setJoinOpen(false)
    sessionStorage.removeItem(sessionStoreKey)
    void endSession().catch(() => undefined) // already gone server-side is fine
  }

  const connectedCount = live.snapshot?.participants.filter((p) => p.connected).length ?? 0

  // ---- Remote play (desktop tunnel; friends join over the internet) ----
  const [remoteUrl, setRemoteUrl] = useState<string | null>(null)
  const [remoteBusy, setRemoteBusy] = useState(false)
  useEffect(() => {
    if (!desktop) return
    void desktop.remote.get().then((s) => setRemoteUrl(s.url)).catch(() => undefined)
    // The shell reports tunnel death (process exit, sidecar restart) — the
    // QR must fall back to wifi URLs rather than advertise a dead link.
    return desktop.remote.onState((s) => setRemoteUrl(s.url))
  }, [])
  const startRemote = async () => {
    if (!desktop || remoteBusy) return
    setRemoteBusy(true)
    try {
      const { url } = await desktop.remote.start()
      setRemoteUrl(url)
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Could not open the tunnel', { kind: 'error' })
    } finally {
      setRemoteBusy(false)
    }
  }
  const stopRemote = () => {
    void desktop?.remote.stop()
    setRemoteUrl(null)
  }

  // A phone join can CREATE a board player server-side — the board query has
  // no way to know, so scoreboard/podium/award rows would go stale. Detect
  // live-scoreboard names missing from the cached board and resync. Keyed on
  // the joined-name set (and re-run when the board lands) with an
  // actually-missing guard, so a refetch that adds the player ends the cycle.
  const queryClient = useQueryClient()
  const joinedNames = session
    ? (live.snapshot?.scoreboard.map((p) => p.name).join('\n') ?? '')
    : ''
  useEffect(() => {
    if (!joinedNames) return
    // Server adopts the board's casing for names — compare case-insensitively.
    const known = new Set(board.players.map((p) => p.name.toLowerCase()))
    if (joinedNames.split('\n').some((name) => !known.has(name.toLowerCase()))) {
      void queryClient.invalidateQueries({ queryKey: boardQuery(boardId).queryKey })
    }
  }, [joinedNames, board, boardId, queryClient])

  // name → phone-connected, for the scoreboard presence dots. Gated on the
  // session (not just the snapshot) — a stale snapshot survives session end.
  const presence =
    session && live.snapshot
      ? new Map(live.snapshot.scoreboard.map((p) => [p.name, p.connected] as const))
      : undefined

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

  const openOverlay = (row: number, col: number, fresh = false) => {
    const cell = board.cells[row]?.[col]
    if (cell) setOverlay({ row, col, cell, fresh })
  }

  const onOpenCell = (row: number, col: number) => {
    // Only reachable playerless by deleting everyone mid-game in the editor —
    // the lobby gates every normal path. One belt-and-suspenders check.
    if (board.players.length === 0) {
      toast('No players — friends can join via Host game, or add them in the editor', {
        kind: 'error',
      })
      return
    }
    // Legacy parity: the cell is marked used the moment it opens, not on award.
    playSfx('pick')
    clueAwardsRef.current = []
    openOverlay(row, col, true)
    actions.setCellUsed.mutate([row, col, true])
  }

  // ---- Turn order (board control) ----
  const giveControl = (name: string | null, announce = false) => {
    actions.setControl.mutate([name])
    if (announce && name) toast(`🎯 ${name} has the board`)
  }

  // First pick: an automatic mode with nobody in control assigns per the
  // first_pick rule ('host' waits for a manual handoff). The fired-ref keeps
  // board refetches from double-picking while the mutation is in flight; it
  // re-arms once control lands (or clears — a fresh game re-picks).
  const firstPickFiredRef = useRef(false)
  useEffect(() => {
    if (board.control_player !== null) {
      firstPickFiredRef.current = false
      return
    }
    // The lobby owns the who-starts moment (roulette on Start) — this effect
    // is only the fallback for games that skipped it (mid-game refreshes).
    if (inLobby) return
    if (board.turn_mode === 'manual' || board.first_pick === 'host') return
    // GAME-START only (no scoring yet): mid-game, a null control can be a
    // deliberate clear (multi-award 'host' with several scorers) — re-picking
    // randomly would stomp it. Score resets clear history, so a fresh game
    // still re-picks.
    if (board.history.length > 0) return
    if (board.players.length === 0 || firstPickFiredRef.current) return
    firstPickFiredRef.current = true
    const pick =
      board.first_pick === 'lowest'
        ? board.players.reduce((low, p) => (p.score < low.score ? p : low))
        : board.players[Math.floor(Math.random() * board.players.length)]
    actions.setControl.mutate([pick.name])
    toast(`🎯 ${pick.name} starts with the board`)
  }, [board, actions.setControl, inLobby])

  // Players awarded (positive) during the open clue, in order, deduped — the
  // input to the close-time control decision below.
  const clueAwardsRef = useRef<string[]>([])

  /** Control transfers are decided when a FRESH clue CLOSES ("after every
   * round"), so "when several players score" means what it says — a single
   * correct answer always takes the board under first-correct, whatever the
   * multi-award rule. Reviews never move control. */
  const closeOverlay = () => {
    const awards = clueAwardsRef.current
    clueAwardsRef.current = []
    if (overlay?.fresh && board.players.length > 0) {
      if (board.turn_mode === 'sequential') {
        const i = board.players.findIndex((p) => p.name === board.control_player)
        const next = board.players[(i + 1) % board.players.length]
        giveControl(next.name, true)
      } else if (board.turn_mode === 'manual') {
        // Least-confusing manual flow: the pick clears after every clue.
        if (board.control_player !== null) giveControl(null)
      } else if (board.turn_mode === 'first-correct') {
        if (awards.length === 1) {
          giveControl(awards[0], true)
        } else if (awards.length >= 2) {
          if (board.multi_award === 'first') giveControl(awards[0], true)
          else if (board.multi_award === 'last') giveControl(awards[awards.length - 1], true)
          // 'host': clear — a stale holder would mislead; the host hands it out.
          else if (board.control_player !== null) giveControl(null)
        }
        // 0 awards → nobody was right: the picker keeps the board.
      }
    }
    setOverlay(null)
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
      {/* ---- Lobby phase: the board never renders playerless ---- */}
      {inLobby && (
        <LobbyScreen
          board={board}
          session={session}
          snapshot={session ? live.snapshot : null}
          creating={creating}
          onHostGame={() => void hostGame(false)}
          onEndSession={endLiveSession}
          remoteUrl={remoteUrl}
          remoteBusy={remoteBusy}
          onStartRemote={desktop ? () => void startRemote() : undefined}
          onStopRemote={stopRemote}
          command={live.command}
          onOpenRules={() => setRulesOpen(true)}
          onStart={(firstPick) => {
            if (firstPick) actions.setControl.mutate([firstPick])
            setInLobby(false)
          }}
          onTogglePresent={togglePresent}
        />
      )}

      {/* ---- Top bar ---- */}
      {!inLobby && (
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
              {/* THE reset: same semantics as the podium's Play again —
                  everything fresh, back to the lobby, roulette re-rolls.
                  (Cells-only resets live on the right-click menu.) */}
              <Button variant="danger" onClick={() => setConfirmNewGame(true)}>
                <RotateCcw className="size-4" />
                New game
              </Button>
              <NegativesToggle
                checked={board.allow_negatives}
                onChange={(v) => actions.setAllowNegatives.mutate([v])}
              />
              <Button variant="ghost" onClick={() => setRulesOpen(true)} title="Game rules — turn order">
                <ListOrdered className="size-4" />
                Rules
              </Button>
            </>
          )}
        </div>
        <div className="text-center">
          <h1 className="font-display text-accent text-2xl font-bold tracking-[0.3em]">
            RHUBARB!
          </h1>
          <p className="text-ink-muted mt-0.5 text-xs">{board.name}</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {!presenting && (
            <>
              {session ? (
                <Button
                  variant="soft"
                  className="border-accent/70 text-accent hover:text-accent hover:border-accent"
                  onClick={() => setJoinOpen(true)}
                  title="Hosted game — show the join panel"
                >
                  <Users className="size-4" />
                  Room {session.code} · {connectedCount}
                </Button>
              ) : (
                <Button
                  variant="soft"
                  onClick={() => void hostGame()}
                  disabled={creating}
                  title="Host a game — phones join as buzzers"
                >
                  <Wifi className="size-4" />
                  Host game
                </Button>
              )}
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
      )}

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
      {!inLobby && (
      <div className="flex min-h-0 flex-1 gap-3 px-3 pb-3">
        <BoardGrid board={board} onOpenCell={onOpenCell} onUsedCellMenu={onUsedCellMenu} />
        <Scoreboard
          players={board.players}
          history={board.history}
          presence={presence}
          controlPlayer={board.control_player}
          handOffAlwaysVisible={board.turn_mode === 'manual'}
          onGiveControl={(name) => giveControl(name, true)}
          onResetScores={() => setConfirmScoreReset(true)}
          onSetScore={(name, score) => actions.setScore.mutate([name, score, 'manual edit'])}
          onUndo={() => actions.undoScore.mutate([])}
        />
      </div>
      )}

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
            if (delta > 0 && !clueAwardsRef.current.includes(name)) {
              clueAwardsRef.current.push(name)
            }
          }}
          onClose={closeOverlay}
          buzzer={session ? (live.snapshot?.buzzer ?? null) : null}
          onBuzzerCommand={session ? live.command : undefined}
          controlPlayer={board.control_player}
          topRowValue={Math.max(0, ...board.row_values)}
        />
      )}

      {/* ---- Hosted-session join panel ---- */}
      {session && (
        <JoinPanel
          open={joinOpen}
          code={session.code}
          lanIps={session.lanIps}
          remoteUrl={remoteUrl}
          remoteBusy={remoteBusy}
          onStartRemote={desktop ? () => void startRemote() : undefined}
          onStopRemote={desktop ? stopRemote : undefined}
          snapshot={live.snapshot}
          command={live.command}
          onEnd={endLiveSession}
          onClose={() => setJoinOpen(false)}
        />
      )}

      {/* ---- Podium (works during present mode — it's FOR the TV) ---- */}
      {podium && (
        <PodiumOverlay
          players={board.players}
          onPlayAgain={() => {
            actions.resetScores.mutate([])
            actions.resetUsed.mutate([])
            // Full circle: a fresh game returns to the lobby — re-invite,
            // re-roll who starts (the session and roster carry over).
            setInLobby(true)
          }}
          onClose={() => setPodium(false)}
        />
      )}

      <ContextMenu state={menu} onClose={() => setMenu(null)} />

      <RulesDialog
        open={rulesOpen}
        board={board}
        onChange={(rules) => actions.setRules.mutate([rules])}
        onClose={() => setRulesOpen(false)}
      />

      <ConfirmDialog
        open={confirmNewGame}
        title="New game"
        message="Reset all scores and the board, and head back to the lobby? Connected players stay in the room."
        confirmLabel="New game"
        danger
        onConfirm={() => {
          actions.resetScores.mutate([])
          actions.resetUsed.mutate([])
          setConfirmNewGame(false)
          setInLobby(true)
        }}
        onCancel={() => setConfirmNewGame(false)}
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
      <ConfirmDialog
        open={lanPrompt}
        title="Wifi access is off"
        message="Phones join over your wifi network, but the app isn't accepting wifi connections yet. Turn it on and the app will reload — then hit Host game again."
        confirmLabel="Turn on & reload"
        onConfirm={() => void desktop?.lan.set(true)}
        onCancel={() => setLanPrompt(false)}
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
