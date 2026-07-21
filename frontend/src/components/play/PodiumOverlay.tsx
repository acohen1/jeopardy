/** PodiumOverlay — end-of-game celebration, designed for the TV (works during
 * present mode). Standings sorted by score desc with shared ranks on ties;
 * top three get podium blocks (1st tallest, center, crowned), the rest a
 * simple list. Pure-CSS confetti falls behind everything — the keyframes are
 * rendered locally so styles.css stays untouched. Fanfare plays on mount
 * (governed by the sfx mute). 'Play again' resets scores + board after a
 * confirm; Esc or 'Close' just closes. */
import { clsx } from 'clsx'
import { useEffect, useMemo, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useHotkeys } from '@/hooks/useHotkeys'
import { money } from '@/lib/format'
import { playSfx } from '@/lib/sfx'
import type { Player } from '@/types/board'

export interface PodiumOverlayProps {
  players: Player[]
  /** Reset scores + board for a new game (called after the confirm). */
  onPlayAgain: () => void
  onClose: () => void
}

interface Ranked extends Player {
  /** Standard competition ranking — ties share a rank (1, 1, 3, …). */
  rank: number
}

function rankPlayers(players: Player[]): Ranked[] {
  const sorted = [...players].sort((a, b) => b.score - a.score)
  let rank = 0
  return sorted.map((p, i) => {
    if (i === 0 || p.score !== sorted[i - 1].score) rank = i + 1
    return { ...p, rank }
  })
}

/* ---- Confetti (pure CSS, palette colors) ---- */
const CONFETTI_COLORS = ['bg-accent', 'bg-accent-bright', 'bg-dollar', 'bg-ink'] as const

interface ConfettiPiece {
  left: number
  delay: number
  duration: number
  size: number
  color: string
}

function makeConfetti(count: number): ConfettiPiece[] {
  return Array.from({ length: count }, (_, i) => ({
    left: Math.random() * 100,
    delay: Math.random() * 4,
    duration: 3.5 + Math.random() * 3,
    size: 6 + Math.random() * 6,
    color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
  }))
}

const CONFETTI_KEYFRAMES = `
@keyframes podium-confetti-fall {
  0%   { transform: translateY(0) rotate(0deg); opacity: 1; }
  100% { transform: translateY(115vh) rotate(720deg); opacity: 0.6; }
}
`

/* Podium block styling per sorted position (0 = winner). */
const BLOCKS = [
  { height: 'h-44', order: 'order-2', numeral: '1' },
  { height: 'h-32', order: 'order-1', numeral: '2' },
  { height: 'h-24', order: 'order-3', numeral: '3' },
] as const

export function PodiumOverlay({ players, onPlayAgain, onClose }: PodiumOverlayProps) {
  const [confirmReset, setConfirmReset] = useState(false)

  const ranked = useMemo(() => rankPlayers(players), [players])
  const podium = ranked.slice(0, 3)
  const rest = ranked.slice(3)

  const confetti = useMemo(() => makeConfetti(40), [])

  useEffect(() => {
    playSfx('fanfare')
  }, [])

  useHotkeys({ Escape: onClose })

  return (
    <div className="bg-bg-deep animate-fade-in fixed inset-0 z-40 flex flex-col overflow-hidden px-8 py-8">
      {/* Locally-scoped keyframes — do not touch styles.css */}
      <style>{CONFETTI_KEYFRAMES}</style>

      {/* Confetti layer (behind content) */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        {confetti.map((c, i) => (
          <span
            key={i}
            className={clsx('absolute rounded-[2px]', c.color)}
            style={{
              left: `${c.left}%`,
              top: '-5vh',
              width: c.size,
              height: c.size * 1.6,
              animation: `podium-confetti-fall ${c.duration}s linear ${c.delay}s infinite`,
            }}
          />
        ))}
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col items-center">
        <h1 className="font-display text-accent mt-2 shrink-0 text-4xl font-bold tracking-[0.25em]">
          FINAL STANDINGS
        </h1>

        {players.length === 0 ? (
          <p className="text-ink-muted mt-16 text-lg">No players — add them in the editor</p>
        ) : (
          <div className="mt-auto mb-auto flex min-h-0 w-full flex-col items-center gap-8 overflow-y-auto py-8">
            {/* ---- Top three podium ---- */}
            <div className="flex items-end justify-center gap-4">
              {podium.map((p, i) => (
                <div
                  key={p.name}
                  className={clsx('flex w-44 flex-col items-center gap-2', BLOCKS[i].order)}
                >
                  {i === 0 && (
                    <span aria-hidden className="text-4xl leading-none">
                      👑
                    </span>
                  )}
                  <p className="text-ink max-w-full truncate px-1 text-center text-lg font-bold">
                    {p.name}
                  </p>
                  <p className="text-dollar font-display text-2xl font-bold">{money(p.score)}</p>
                  <div
                    className={clsx(
                      'bg-surface-warm border-line-soft flex w-full items-start justify-center rounded-t-xl border border-b-0 pt-3',
                      BLOCKS[i].height,
                    )}
                  >
                    <span
                      className={clsx(
                        'font-display text-5xl font-bold',
                        i === 0 ? 'text-accent-bright' : 'text-ink-faint',
                      )}
                    >
                      {p.rank}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* ---- Everyone else ---- */}
            {rest.length > 0 && (
              <ul className="w-full max-w-md shrink-0 space-y-1.5">
                {rest.map((p) => (
                  <li
                    key={p.name}
                    className="bg-surface/60 border-line-soft flex items-center gap-3 rounded-lg border px-4 py-2"
                  >
                    <span className="text-ink-faint w-6 shrink-0 text-right text-sm font-bold tabular-nums">
                      {p.rank}
                    </span>
                    <span className="text-ink min-w-0 flex-1 truncate text-sm font-semibold">
                      {p.name}
                    </span>
                    <span className="text-dollar shrink-0 text-sm font-bold tabular-nums">
                      {money(p.score)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* ---- Footer ---- */}
        <div className="flex shrink-0 items-center gap-3 pb-2">
          <Button variant="danger" onClick={() => setConfirmReset(true)}>
            Play again
          </Button>
          <Button variant="ghost" onClick={onClose} title="Close [Esc]">
            Close
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmReset}
        title="Play again"
        message="Reset scores and board for a new game?"
        confirmLabel="Reset"
        danger
        onConfirm={() => {
          setConfirmReset(false)
          onPlayAgain()
          onClose()
        }}
        onCancel={() => setConfirmReset(false)}
      />
    </div>
  )
}
