/** ClueTimer — host countdown for the clue overlay top bar.
 *  - Idle: compact ghost button showing the last-used duration ("30s").
 *  - Click or 'T' starts/restarts; running state renders an SVG ring that
 *    drains smoothly with the remaining whole seconds centered.
 *  - At zero: ring + number turn danger and pulse, plus a soft double beep
 *    (playSfx('timeUp') — governed by the app-wide sfx mute).
 *    Stays expired until clicked again (restart).
 *  - Right-click → preset menu (10/20/30/60s) which persists + starts.
 * Duration persists in localStorage 'clue-timer-duration'. Mounted outside
 * the keyed SlideView so the countdown survives question↔answer flips. */
import { clsx } from 'clsx'
import { Timer } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'

import { Button } from '@/components/ui/Button'
import { ContextMenu, type ContextMenuState } from '@/components/ui/ContextMenu'
import { useHotkeys } from '@/hooks/useHotkeys'
import { playSfx } from '@/lib/sfx'

const STORAGE_KEY = 'clue-timer-duration'
const PRESETS = [10, 20, 30, 60]

function loadDuration(): number {
  try {
    const n = Number(localStorage.getItem(STORAGE_KEY))
    return Number.isFinite(n) && n > 0 ? n : 30
  } catch {
    return 30
  }
}

const RADIUS = 15.5
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export function ClueTimer() {
  const [duration, setDuration] = useState(loadDuration)
  const [status, setStatus] = useState<'idle' | 'running' | 'expired'>('idle')
  const [remaining, setRemaining] = useState(0)
  const [menu, setMenu] = useState<ContextMenuState | null>(null)

  const intervalRef = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearInterval(intervalRef.current), [])

  const start = (secs = duration) => {
    window.clearInterval(intervalRef.current)
    const end = Date.now() + secs * 1000
    setStatus('running')
    setRemaining(secs)
    intervalRef.current = window.setInterval(() => {
      const rem = (end - Date.now()) / 1000
      if (rem <= 0) {
        window.clearInterval(intervalRef.current)
        setRemaining(0)
        setStatus('expired')
        playSfx('timeUp')
      } else {
        setRemaining(rem)
      }
    }, 100)
  }

  useHotkeys({ t: () => start() })

  const openMenu = (e: ReactMouseEvent) => {
    e.preventDefault()
    setMenu({
      x: e.clientX,
      y: e.clientY,
      items: PRESETS.map((p) => ({
        label: `${p}s`,
        onSelect: () => {
          try {
            localStorage.setItem(STORAGE_KEY, String(p))
          } catch {
            // Persistence is best-effort.
          }
          setDuration(p)
          start(p)
        },
      })),
    })
  }

  if (status === 'idle') {
    return (
      <>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => start()}
          onContextMenu={openMenu}
          title="Start timer [T] · right-click for presets"
        >
          <Timer className="size-4" />
          {duration}s
        </Button>
        <ContextMenu state={menu} onClose={() => setMenu(null)} />
      </>
    )
  }

  const expired = status === 'expired'
  const frac = duration > 0 ? remaining / duration : 0
  return (
    <>
      <button
        type="button"
        onClick={() => start()}
        onContextMenu={openMenu}
        title={expired ? "Time's up — click to restart [T]" : 'Restart timer [T]'}
        className={clsx('relative size-9 shrink-0 cursor-pointer', expired && 'animate-pulse')}
      >
        <svg viewBox="0 0 36 36" className="size-9 -rotate-90">
          <circle
            cx="18"
            cy="18"
            r={RADIUS}
            fill="none"
            strokeWidth="3"
            className="stroke-line-soft"
          />
          <circle
            cx="18"
            cy="18"
            r={RADIUS}
            fill="none"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - frac)}
            className={expired ? 'stroke-danger' : 'stroke-accent'}
          />
        </svg>
        <span
          className={clsx(
            'absolute inset-0 flex items-center justify-center text-xs font-bold tabular-nums',
            expired ? 'text-danger' : 'text-ink',
          )}
        >
          {Math.ceil(remaining)}
        </span>
      </button>
      <ContextMenu state={menu} onClose={() => setMenu(null)} />
    </>
  )
}
