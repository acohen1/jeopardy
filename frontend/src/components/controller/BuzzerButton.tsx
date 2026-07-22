import { clsx } from 'clsx'
import { useEffect, useRef, useState } from 'react'

import type { BuzzerState } from '@/lib/live'
import { playSfx } from '@/lib/sfx'

interface BuzzerButtonProps {
  buzzer: BuzzerState
  /** This player's name (identity within the session). */
  you: string
  buzz: () => void
}

/** True while a form field owns the keyboard — swallow the buzz keys then. */
function typingTarget(): boolean {
  const el = document.activeElement
  return (
    el instanceof HTMLElement &&
    (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
  )
}

/** Mirrors the server's FALSE_START_PENALTY (session.py) — buzzing before
 * the arm freezes your buzzer briefly; each early press re-triggers it. The
 * server enforces this with its own clock; this copy just makes it FELT. */
const FALSE_START_MS = 500

/** The giant round buzzer. Fires on pointerdown for minimum latency — one
 * event for touch, mouse, and pen alike (no click handler, so the click a
 * tap synthesizes can't double-buzz). Space/Enter buzz too while armed, so
 * laptop players compete on equal footing. */
export function BuzzerButton({ buzzer, you, buzz }: BuzzerButtonProps) {
  // The server adopts the board's casing for names ("sakura" → "Sakura"),
  // so every identity comparison must be case-insensitive.
  const me = you.trim().toLowerCase()
  const lockedOut =
    buzzer.phase !== 'locked' && buzzer.lockedOut.some((n) => n.toLowerCase() === me)
  const canBuzz = buzzer.phase === 'armed' && !lockedOut
  const wonByYou = buzzer.phase === 'won' && buzzer.winner.toLowerCase() === me

  // Anti-cheese: pressing during WAIT (or while still frozen from doing so)
  // is a false start — brief personal freeze + "Too soon" flash.
  const frozenUntilRef = useRef(0)
  const [tooSoonAt, setTooSoonAt] = useState<number | null>(null)
  useEffect(() => {
    if (tooSoonAt === null) return
    const t = window.setTimeout(() => setTooSoonAt(null), 900)
    return () => window.clearTimeout(t)
  }, [tooSoonAt])

  const press = () => {
    const now = Date.now()
    if (buzzer.phase === 'locked' || (canBuzz && now < frozenUntilRef.current)) {
      frozenUntilRef.current = now + FALSE_START_MS
      setTooSoonAt(now)
      navigator.vibrate?.(80)
      return
    }
    if (canBuzz) buzz()
  }
  const pressRef = useRef(press)
  pressRef.current = press

  // Evaluated once: the device's pointer class doesn't change mid-session.
  const [finePointer] = useState(() => window.matchMedia('(pointer: fine)').matches)

  // Celebrate a win exactly once — snapshots rebroadcast on every join/drop.
  const celebratedRef = useRef(false)
  useEffect(() => {
    if (wonByYou && !celebratedRef.current) {
      celebratedRef.current = true
      playSfx('correct')
    }
    if (buzzer.phase !== 'won') celebratedRef.current = false
  }, [wonByYou, buzzer.phase])

  // Listen while WAITING too — false starts must be felt, not swallowed.
  const keysLive = canBuzz || buzzer.phase === 'locked'
  useEffect(() => {
    if (!keysLive) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.repeat || (e.key !== ' ' && e.key !== 'Enter') || typingTarget()) return
      e.preventDefault() // no page scroll, no focused-button click on top
      pressRef.current()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [keysLive])

  let label: string
  let style: string
  if (buzzer.phase === 'locked') {
    label = 'WAIT'
    style = 'bg-surface text-ink-faint border-4 border-line-soft'
  } else if (buzzer.phase === 'armed') {
    if (lockedOut) {
      label = 'LOCKED OUT'
      style = 'bg-surface text-ink-faint border-4 border-line-soft'
    } else {
      label = 'BUZZ!'
      style =
        'bg-accent-deep text-ink border-4 border-accent shadow-[0_0_48px_rgba(125,175,141,0.5)] active:scale-95 animate-scale-in'
    }
  } else if (wonByYou) {
    label = '🎉 YOU!'
    style = 'bg-dollar/25 text-dollar border-4 border-dollar animate-scale-in'
  } else {
    label = `${buzzer.winner} buzzed in`
    style = 'bg-surface text-ink-muted border-4 border-line-soft'
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <button
        type="button"
        // Stays ENABLED during WAIT so false starts register (and penalize);
        // truly inert only when locked out or someone already won.
        disabled={buzzer.phase === 'won' || lockedOut}
        onPointerDown={(e) => {
          // Primary button/touch/pen only — right and middle click must not buzz.
          if (e.button !== 0) return
          press()
        }}
        aria-label={canBuzz ? 'Buzz in' : label}
        className={clsx(
          // Height-capped so the whole column fits a laptop screen upright.
          'font-display aspect-square w-[min(80vw,40vh,24rem)] rounded-full text-3xl font-bold',
          'flex items-center justify-center px-8 text-center break-words select-none',
          'touch-manipulation transition-transform duration-75 [-webkit-tap-highlight-color:transparent]',
          !canBuzz && 'cursor-default',
          style,
        )}
      >
        {label}
      </button>
      {tooSoonAt !== null ? (
        <p key={tooSoonAt} className="text-danger animate-scale-in text-xs font-bold">
          Too soon — wait for it…
        </p>
      ) : (
        finePointer && <p className="text-ink-faint text-xs">or press Space</p>
      )}
    </div>
  )
}
