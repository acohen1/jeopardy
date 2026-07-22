/** LobbyScreen — the pre-game phase of play mode (edit → LOBBY → board).
 *
 * The TV-facing invitation: host a room (giant code + QR), watch the roster
 * fill as phones join, then hit Start. The board never renders without
 * players, so playerless edge cases are structurally unreachable rather
 * than defensively checked. Under random first pick, Start runs a roulette
 * sweep across the roster before the winner is announced.
 * Purely presentational — session lifecycle and control mutations stay in
 * PlayMode (onHostGame / onEndSession / onStart). */
import { clsx } from 'clsx'
import { Globe, ListOrdered, Pencil, Play, Presentation, UserX, Wifi } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from '@tanstack/react-router'

import { Button } from '@/components/ui/Button'
import { joinUrl, type HostCommand, type SessionCreated, type SessionSnapshot } from '@/lib/live'
import { playSfx } from '@/lib/sfx'
import type { Board } from '@/types/board'

import { JoinQr } from './JoinInfo'

export interface LobbyScreenProps {
  board: Board
  session: SessionCreated | null
  snapshot: SessionSnapshot | null
  creating: boolean
  onHostGame: () => void
  onEndSession: () => void
  /* ---- Remote play (desktop only; absent hides the affordance) ---- */
  remoteUrl: string | null
  remoteBusy: boolean
  onStartRemote?: () => void
  onStopRemote: () => void
  command: (command: HostCommand, target?: string) => void
  onOpenRules: () => void
  /** Leave the lobby; `firstPick` is the roulette/lowest winner (or null). */
  onStart: (firstPick: string | null) => void
  onTogglePresent: () => void
}

const TURN_LABEL: Record<Board['turn_mode'], string> = {
  'first-correct': 'First correct answer picks next',
  sequential: 'Taking turns in order',
  manual: 'Host hands the board around',
}

export function LobbyScreen({
  board,
  session,
  snapshot,
  creating,
  onHostGame,
  onEndSession,
  remoteUrl,
  remoteBusy,
  onStartRemote,
  onStopRemote,
  command,
  onOpenRules,
  onStart,
  onTogglePresent,
}: LobbyScreenProps) {
  const [highlight, setHighlight] = useState<number | null>(null)
  const [landed, setLanded] = useState<string | null>(null)
  const rolling = highlight !== null || landed !== null
  const timerRef = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timerRef.current), [])

  const connected = new Map(
    (snapshot?.scoreboard ?? []).map((p) => [p.name, p.connected] as const),
  )
  const participants = new Set((snapshot?.participants ?? []).map((p) => p.name))

  const lanUrl = session ? joinUrl(session.lanIps[0]) : null
  const extraUrls = session ? session.lanIps.slice(1).map((ip) => joinUrl(ip)) : []
  // Remote tunnel active → the QR serves EVERYONE (wifi friends included);
  // the wifi addresses stay listed as alternates.
  const primaryUrl = session ? (remoteUrl ? `${remoteUrl}/join` : lanUrl) : null

  const startGame = () => {
    if (board.players.length === 0 || rolling) return
    const wantsAutoPick =
      board.turn_mode !== 'manual' &&
      board.first_pick !== 'host' &&
      board.control_player === null
    if (!wantsAutoPick) {
      onStart(null)
      return
    }
    if (board.first_pick === 'lowest') {
      const low = board.players.reduce((a, b) => (b.score < a.score ? b : a))
      setLanded(low.name)
      playSfx('correct')
      timerRef.current = window.setTimeout(() => onStart(low.name), 1300)
      return
    }
    // Random → roulette: one full sweep plus the run-in, decelerating.
    const n = board.players.length
    const target = Math.floor(Math.random() * n)
    const hops = n + target + 1
    let i = 0
    const hop = (delay: number) => {
      timerRef.current = window.setTimeout(() => {
        setHighlight(i % n)
        playSfx('pick')
        i += 1
        if (i < hops) {
          hop(Math.min(delay * 1.22, 260))
        } else {
          setHighlight(null)
          setLanded(board.players[target].name)
          playSfx('correct')
          timerRef.current = window.setTimeout(() => onStart(board.players[target].name), 1300)
        }
      }, delay)
    }
    hop(70)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col px-6 py-4">
      {/* ---- Lobby chrome ---- */}
      <header className="grid shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-4">
        <div>
          <Link
            to="/boards/$boardId/edit"
            params={{ boardId: board.id }}
            className="text-ink-muted border-line/60 hover:bg-surface hover:text-ink hover:border-line inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-1.5 text-sm transition-colors duration-100"
          >
            <Pencil className="size-3.5" />
            Edit board
          </Link>
        </div>
        <div className="text-center">
          <h1 className="font-display text-accent text-2xl font-bold tracking-[0.3em]">
            JEOPARDY!
          </h1>
          <p className="text-ink-muted mt-0.5 text-xs">{board.name}</p>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onOpenRules} title="Game rules — turn order">
            <ListOrdered className="size-4" />
            Rules
          </Button>
          <Button variant="soft" onClick={onTogglePresent} title="Present mode [P]">
            <Presentation className="size-4" />
            Present
          </Button>
        </div>
      </header>

      {/* ---- Invitation + roster ---- */}
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-8 lg:flex-row lg:gap-16">
        {/* Join zone */}
        <div className="flex flex-col items-center gap-5 text-center">
          {session && primaryUrl ? (
            <>
              <div>
                <p className="text-accent text-xs font-bold tracking-widest uppercase">
                  Room code
                </p>
                <p className="font-display text-dollar text-7xl font-bold tracking-widest">
                  {session.code}
                </p>
              </div>
              <JoinQr url={primaryUrl} className="w-52" />
              <div>
                {remoteUrl && (
                  <p className="text-accent mb-1 inline-flex items-center gap-1.5 text-xs font-semibold">
                    <Globe className="size-3.5" />
                    Anyone can join — near or far
                  </p>
                )}
                <p className="text-ink font-mono text-sm break-all">{primaryUrl}</p>
                {remoteUrl && lanUrl && (
                  <p className="text-ink-faint mt-0.5 font-mono text-xs break-all">
                    on this wifi: {lanUrl}
                  </p>
                )}
                {extraUrls.map((u) => (
                  <p key={u} className="text-ink-faint mt-0.5 font-mono text-xs break-all">
                    or {u}
                  </p>
                ))}
              </div>
              <div className="flex items-center gap-2">
                {remoteUrl ? (
                  <Button variant="ghost" onClick={onStopRemote} className="text-xs">
                    <Globe className="size-3.5" />
                    Stop remote access
                  </Button>
                ) : (
                  onStartRemote && (
                    <Button
                      variant="soft"
                      onClick={onStartRemote}
                      disabled={remoteBusy}
                      title="Open a secure tunnel so friends can join from anywhere"
                    >
                      <Globe className="size-4" />
                      {remoteBusy ? 'Opening tunnel…' : 'Invite over the internet'}
                    </Button>
                  )
                )}
                <Button variant="ghost" onClick={onEndSession} className="text-xs">
                  End session
                </Button>
              </div>
            </>
          ) : (
            <>
              <Button
                variant="primary"
                size="lg"
                onClick={onHostGame}
                disabled={creating}
                className="px-8"
              >
                <Wifi className="size-5" />
                Host game
              </Button>
              <p className="text-ink-muted max-w-60 text-sm leading-relaxed">
                Friends join from their phones over wifi — or add players in the editor.
              </p>
            </>
          )}
        </div>

        {/* Roster */}
        <div className="w-full max-w-sm" data-testid="lobby-roster">
          <p className="text-accent mb-2 text-xs font-bold tracking-widest uppercase">
            Players · {board.players.length}
          </p>
          {board.players.length === 0 ? (
            <p className="text-ink-muted text-sm leading-relaxed">
              Nobody yet — waiting for phones to join{session ? '' : ' (host a game!)'}, or
              add players in the editor.
            </p>
          ) : (
            <ul className="max-h-[45vh] space-y-1.5 overflow-y-auto pr-1">
              {board.players.map((p, i) => {
                const isLanded = landed === p.name
                return (
                  <li
                    key={p.name}
                    className={clsx(
                      'flex items-center gap-2.5 rounded-xl border px-3.5 py-2 text-sm transition-colors duration-75',
                      isLanded
                        ? 'border-dollar bg-dollar/15'
                        : highlight === i
                          ? 'border-accent bg-accent/15'
                          : 'border-line-soft bg-surface-warm',
                    )}
                  >
                    <span
                      className={clsx(
                        'size-2 shrink-0 rounded-full',
                        connected.get(p.name) ? 'bg-accent' : 'bg-ink-faint',
                      )}
                      title={connected.get(p.name) ? 'Connected' : 'Not connected'}
                    />
                    <span className="text-ink min-w-0 flex-1 truncate font-semibold">
                      {p.name}
                    </span>
                    {isLanded && (
                      <span className="text-dollar animate-scale-in shrink-0 text-xs font-bold">
                        🎯 starts!
                      </span>
                    )}
                    {participants.has(p.name) && !rolling && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => command('kick', p.name)}
                        title="Disconnect — they can rejoin as themselves"
                        aria-label={`Disconnect ${p.name}`}
                        className="-my-1 shrink-0 border-transparent px-1.5"
                      >
                        <UserX className="size-3.5" />
                      </Button>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>

      {/* ---- Start ---- */}
      <div className="flex shrink-0 flex-col items-center gap-2 pb-4">
        <Button
          variant="primary"
          size="lg"
          data-testid="lobby-start"
          onClick={startGame}
          disabled={board.players.length === 0 || rolling}
          className="px-10"
        >
          <Play className="size-5" fill="currentColor" />
          Start game
        </Button>
        <p className="text-ink-faint text-xs">
          {board.players.length === 0
            ? 'Waiting for at least one player'
            : TURN_LABEL[board.turn_mode]}
        </p>
      </div>
    </div>
  )
}
