/** HistoryPanel — collapsible scoring-history feed inside the scoreboard.
 * Collapsed by default; open/closed persists in localStorage
 * 'play-history-open'. Expanded: latest-first scrollable list. */
import { clsx } from 'clsx'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

import { money } from '@/lib/format'
import type { ScoreEvent } from '@/types/board'

const STORAGE_KEY = 'play-history-open'

function loadOpen(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

/** ISO timestamp → local HH:MM. */
function clock(ts: string): string {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

export function HistoryPanel({ history }: { history: ScoreEvent[] }) {
  const [open, setOpen] = useState(loadOpen)

  const toggle = () =>
    setOpen((v) => {
      try {
        localStorage.setItem(STORAGE_KEY, v ? '0' : '1')
      } catch {
        // Persistence is best-effort.
      }
      return !v
    })

  // History is stored oldest→newest; the feed shows latest first.
  const events = [...history].reverse()

  return (
    <div className="shrink-0">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="text-ink-muted hover:text-ink flex w-full cursor-pointer items-center gap-2 rounded-md px-1 py-1 text-xs font-bold tracking-wide transition-colors duration-100"
      >
        <span>History</span>
        <span className="bg-cell text-ink-faint rounded-full px-1.5 py-px text-[10px] font-bold tabular-nums">
          {history.length}
        </span>
        <ChevronDown
          className={clsx(
            'ml-auto size-3.5 transition-transform duration-150',
            !open && '-rotate-90',
          )}
        />
      </button>

      {open &&
        (events.length === 0 ? (
          <p className="text-ink-faint px-1 py-1.5 text-xs">No scoring yet.</p>
        ) : (
          <ul className="mt-1 max-h-[40vh] space-y-1.5 overflow-y-auto pr-1">
            {events.map((ev, i) => (
              <li key={events.length - i} className="px-1 text-xs leading-snug">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="min-w-0">
                    {ev.kind === 'set' ? (
                      <>
                        <span
                          className={clsx(
                            'font-bold tabular-nums',
                            ev.delta >= 0 ? 'text-accent' : 'text-danger',
                          )}
                        >
                          = {money(ev.after)}
                        </span>{' '}
                        <span className="text-ink-faint">(was {money(ev.before)})</span>
                      </>
                    ) : (
                      <span
                        className={clsx(
                          'font-bold tabular-nums',
                          ev.delta >= 0 ? 'text-accent' : 'text-danger',
                        )}
                      >
                        {ev.delta >= 0 ? '+' : '−'}
                        {money(Math.abs(ev.delta))}
                      </span>
                    )}{' '}
                    <span className="text-ink font-bold break-words">{ev.player}</span>
                  </span>
                  <span className="text-ink-faint shrink-0 tabular-nums">{clock(ev.ts)}</span>
                </div>
                {ev.note && <p className="text-ink-faint text-[11px]">{ev.note}</p>}
              </li>
            ))}
          </ul>
        ))}
    </div>
  )
}
