import { clsx } from 'clsx'
import { useEffect, useState } from 'react'

import { BuzzerButton } from '@/components/controller/BuzzerButton'
import { useWakeLock } from '@/components/controller/useWakeLock'
import { money } from '@/lib/format'
import type { ConnectionPhase, LiveState, SessionSnapshot } from '@/lib/live'

interface ControllerScreenProps {
  you: string
  snapshot: SessionSnapshot
  phase: ConnectionPhase
  lastResult: LiveState['lastResult']
  buzz: () => void
}

/** A result flash in flight: the award event plus its exit-fade flag. */
interface Flash {
  player: string
  delta: number
  at: number
  mine: boolean
  leaving: boolean
}

/** "+$400!" for gains, "−$400" for losses (typographic minus, host parity). */
function fmtDelta(delta: number, excited: boolean): string {
  if (delta >= 0) return `+${money(delta)}${excited ? '!' : ''}`
  return `−${money(Math.abs(delta))}`
}

/** The in-game controller: identity + score, THE buzzer, live standings.
 * One centered max-w column so it reads as intentional on a laptop while
 * staying pixel-perfect on a 390px phone. */
export function ControllerScreen({ you, snapshot, phase, lastResult, buzz }: ControllerScreenProps) {
  useWakeLock()

  const connected = phase === 'open'
  // The server adopts the board's casing for names ("sakura" → "Sakura"),
  // so find myself case-insensitively and display the adopted spelling.
  const meLower = you.trim().toLowerCase()
  const me = snapshot.scoreboard.find((p) => p.name.toLowerCase() === meLower)
  const standings = [...snapshot.scoreboard].sort((a, b) => b.score - a.score)

  const [flash, setFlash] = useState<Flash | null>(null)
  useEffect(() => {
    if (!lastResult) return
    const mine = lastResult.player.toLowerCase() === meLower
    setFlash({ ...lastResult, mine, leaving: false })
    if (mine) {
      // Short double-tap for a gain, one long buzz for a loss; desktop
      // browsers without vibration just no-op behind the optional call.
      navigator.vibrate?.(lastResult.delta >= 0 ? [40, 60, 40] : 220)
    }
    const fade = window.setTimeout(() => setFlash((f) => (f ? { ...f, leaving: true } : f)), 1100)
    const gone = window.setTimeout(() => setFlash(null), 1400)
    return () => {
      window.clearTimeout(fade)
      window.clearTimeout(gone)
    }
  }, [lastResult, meLower])

  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col items-center px-6 py-5">
      {/* Header: code + connection state, then YOU and your money. */}
      <header className="flex w-full max-w-sm flex-col items-center gap-2">
        <div className="flex w-full items-center justify-between">
          <span className="text-ink-muted font-display text-sm font-bold tracking-widest">
            {snapshot.code}
          </span>
          <span
            className={clsx(
              'rounded-full border px-3 py-1 text-xs font-semibold',
              connected
                ? 'border-accent/50 bg-accent/10 text-accent'
                : 'border-dollar/50 bg-dollar/10 text-dollar',
            )}
          >
            {connected ? 'connected' : 'reconnecting…'}
          </span>
        </div>
        <h1 className="font-display text-ink max-w-full truncate text-4xl font-bold">
          {me?.name ?? you}
        </h1>
        {me && (
          <p
            className={clsx(
              'font-display text-3xl font-bold tabular-nums',
              me.score >= 0 ? 'text-accent' : 'text-danger',
            )}
          >
            {money(me.score)}
          </p>
        )}
        {/* Turn rules: the host's board-control pick, live on every device. */}
        {snapshot.control != null &&
          (snapshot.control.toLowerCase() === meLower ? (
            <span className="border-dollar/60 bg-dollar/15 text-dollar animate-scale-in rounded-full border px-4 py-1 text-sm font-bold">
              🎯 Your pick!
            </span>
          ) : (
            <span className="text-ink-faint text-xs">
              {snapshot.control} has the board
            </span>
          ))}
      </header>

      {/* The buzzer owns the middle of the screen. */}
      <div className="flex flex-1 items-center justify-center py-6">
        <BuzzerButton buzzer={snapshot.buzzer} you={you} buzz={buzz} />
      </div>

      {/* Standings: everyone on the board, richest first, phones dotted. */}
      {standings.length > 0 && (
        <ol className="w-full max-w-sm space-y-1 pb-3">
          {standings.map((p, i) => {
            const isMe = p.name.toLowerCase() === meLower
            return (
              <li
                key={p.name}
                className={clsx(
                  'flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-sm',
                  isMe && 'bg-accent/10',
                )}
              >
                <span className="text-ink-faint w-5 shrink-0 text-right tabular-nums">{i + 1}</span>
                <span
                  aria-hidden
                  className={clsx(
                    'size-2 shrink-0 rounded-full',
                    p.connected ? 'bg-accent' : 'bg-ink-faint',
                  )}
                />
                <span
                  className={clsx(
                    'min-w-0 flex-1 truncate',
                    isMe ? 'text-ink font-bold' : 'text-ink-muted',
                  )}
                >
                  {p.name}
                </span>
                <span
                  className={clsx(
                    'shrink-0 font-semibold tabular-nums',
                    p.score >= 0 ? 'text-dollar' : 'text-danger',
                  )}
                >
                  {money(p.score)}
                </span>
              </li>
            )
          })}
        </ol>
      )}

      {/* My award: full-screen flash. Keyed by `at` so back-to-back awards
       * restart the entrance animation. */}
      {flash && flash.mine && (
        <div
          key={flash.at}
          aria-live="polite"
          className={clsx(
            'pointer-events-none fixed inset-0 z-50 flex items-center justify-center',
            'transition-opacity duration-300',
            flash.leaving && 'opacity-0',
          )}
        >
          <p
            className={clsx(
              'animate-scale-in font-display text-6xl font-bold drop-shadow-[0_4px_24px_rgba(0,0,0,0.6)]',
              flash.delta >= 0 ? 'text-accent' : 'text-danger',
            )}
          >
            {fmtDelta(flash.delta, true)}
          </p>
        </div>
      )}

      {/* Someone else's award: quiet toast up top. */}
      {flash && !flash.mine && (
        <div
          key={flash.at}
          className={clsx(
            'pointer-events-none fixed inset-x-0 top-4 z-50 flex justify-center',
            'transition-opacity duration-300',
            flash.leaving && 'opacity-0',
          )}
        >
          <p className="animate-toast-in bg-surface border-line text-ink-muted shadow-raised rounded-full border px-4 py-1.5 text-sm">
            {flash.player}{' '}
            <span
              className={clsx(
                'font-semibold',
                flash.delta >= 0 ? 'text-accent' : 'text-danger',
              )}
            >
              {fmtDelta(flash.delta, false)}
            </span>
          </p>
        </div>
      )}
    </div>
  )
}
