/** BonusSplash — the "★ BONUS ★" reveal page shown when a bonus (Daily
 * Double) tile is opened fresh. The host picks WHO is wagering (pre-selected
 * to the controlling player under turn rules), sets a wager hard-capped at
 * max(wagerer's score, top row value) — the real Daily Double rule — and
 * reveals the question. Parses/validates and hands (wager, wagerer) up. */
import { useState } from 'react'
import type { FormEvent, KeyboardEvent as ReactKeyboardEvent } from 'react'
import { clsx } from 'clsx'

import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/TextInput'
import { toast } from '@/components/ui/Toaster'
import { money } from '@/lib/format'
import type { Player } from '@/types/board'

export interface BonusSplashProps {
  /** The tile's printed value — the wager default and the base for the chips. */
  tileValue: number
  /** Highest row value on the board — the wager floor for low/negative scores. */
  topRowValue: number
  players: Player[]
  /** Pre-selected wagerer (the controlling player), when turn rules know one. */
  initialWagerer: string | null
  /** Called with the validated wager + wagerer when the host reveals. */
  onSubmit: (wager: number, wagerer: string | null) => void
  /** Esc pressed while typing in the wager field — close the overlay. */
  onCancel: () => void
}

const WAGER_INPUT_ID = 'bonus-wager'

/** TextInput takes no ref prop, so focus/select goes through the id. */
function focusWagerInput() {
  const el = document.getElementById(WAGER_INPUT_ID)
  if (el instanceof HTMLInputElement) {
    el.focus()
    el.select()
  }
}

/** '$1,200' / '1200' / ' 1 200 ' → 1200; NaN when non-numeric or empty. */
function parseWager(raw: string): number {
  const cleaned = raw.replace(/[$,\s]/g, '')
  return cleaned.length > 0 ? Number(cleaned) : NaN
}

export function BonusSplash({
  tileValue,
  topRowValue,
  players,
  initialWagerer,
  onSubmit,
  onCancel,
}: BonusSplashProps) {
  const [raw, setRaw] = useState(String(tileValue))
  const [wagerer, setWagerer] = useState<string | null>(initialWagerer)
  // Turn order usually KNOWS who found the tile — state it, don't ask.
  // The full picker only appears when control is unassigned (host-decides
  // flows) or the host taps "Someone else?".
  const [showPicker, setShowPicker] = useState(initialWagerer === null)

  const selected = players.find((p) => p.name === wagerer) ?? null
  /** Real Daily Double rule: even at $0 (or below) you can risk the board's
   * top clue value; above that, your whole score. */
  const cap = selected ? Math.max(selected.score, topRowValue) : null

  const setFromChip = (amount: number) => {
    setRaw(String(amount))
    // Keep the field ready for an immediate Enter / manual tweak.
    requestAnimationFrame(focusWagerInput)
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (players.length > 0 && !selected) {
      toast('Pick who is wagering first', { kind: 'error' })
      return
    }
    const wager = parseWager(raw)
    if (!Number.isFinite(wager) || wager <= 0) {
      toast('Enter a positive wager', { kind: 'error' })
      focusWagerInput()
      return
    }
    if (cap !== null && wager > cap) {
      toast(`${selected!.name} can wager at most ${money(cap)}`, { kind: 'error' })
      focusWagerInput()
      return
    }
    onSubmit(wager, selected?.name ?? null)
  }

  const onInputKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    // useHotkeys skips typing targets, so Esc-in-field needs its own wiring
    // to keep "Esc closes the overlay" true on this page.
    if (e.key === 'Escape') {
      e.preventDefault()
      onCancel()
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-8">
      {/* Lockup with a soft pulsing amber glow behind it */}
      <div className="animate-scale-in relative">
        <div
          aria-hidden
          className="bg-dollar/25 absolute inset-x-0 inset-y-2 animate-pulse rounded-full blur-3xl"
        />
        <h2 className="font-display text-dollar relative text-6xl font-black tracking-wide md:text-7xl">
          ★ BONUS ★
        </h2>
      </div>

      <div className="space-y-1.5 text-center">
        <p className="text-ink-muted text-lg">This tile is worth whatever you wager.</p>
        <p className="text-ink-faint text-sm">Tile value: {money(tileValue)}</p>
      </div>

      {players.length > 0 &&
        (showPicker ? (
          <div className="space-y-2.5 text-center">
            <p className="text-ink-muted text-sm">Who&rsquo;s wagering?</p>
            <div className="flex max-w-2xl flex-wrap justify-center gap-2">
              {players.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  data-testid={`wagerer-${p.name}`}
                  onClick={() => setWagerer(p.name)}
                  className={clsx(
                    'cursor-pointer rounded-lg border px-3 py-1.5 text-sm transition-colors duration-100',
                    p.name === wagerer
                      ? 'border-dollar bg-dollar/15 text-dollar'
                      : 'border-line/60 text-ink-muted hover:border-line hover:text-ink',
                  )}
                >
                  {p.name}
                  <span className={clsx('ml-2', p.score < 0 && 'text-danger')}>
                    {money(p.score)}
                  </span>
                </button>
              ))}
            </div>
            {selected && cap !== null && (
              <p className="text-ink-faint text-xs">
                {selected.name} can wager up to <span className="text-dollar">{money(cap)}</span>
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-1 text-center" data-testid="wagerer-known">
            <p className="text-ink text-lg">
              <span className="text-dollar font-semibold">{selected?.name ?? wagerer}</span>{' '}
              is wagering
              {cap !== null && (
                <span className="text-ink-muted">
                  {' '}
                  — up to <span className="text-dollar">{money(cap)}</span>
                </span>
              )}
            </p>
            <button
              type="button"
              onClick={() => setShowPicker(true)}
              className="text-ink-faint hover:text-ink cursor-pointer text-xs underline decoration-dotted underline-offset-4"
            >
              Someone else?
            </button>
          </div>
        ))}

      <form onSubmit={submit} className="flex flex-col items-center gap-6">
        <div className="flex flex-wrap items-center justify-center gap-3">
          <label htmlFor={WAGER_INPUT_ID} className="text-ink-muted text-sm">
            Wager
          </label>
          <TextInput
            id={WAGER_INPUT_ID}
            value={raw}
            inputMode="numeric"
            autoFocus
            onFocus={(e) => e.currentTarget.select()}
            onChange={(e) => setRaw(e.target.value)}
            onKeyDown={onInputKeyDown}
            className="w-32 text-center"
          />
          <Button type="button" variant="soft" size="sm" onClick={() => setFromChip(tileValue)}>
            {money(tileValue)}
          </Button>
          <Button type="button" variant="soft" size="sm" onClick={() => setFromChip(tileValue * 2)}>
            2× {money(tileValue * 2)}
          </Button>
          {cap !== null && cap !== tileValue && cap !== tileValue * 2 && (
            <Button type="button" variant="soft" size="sm" onClick={() => setFromChip(cap)}>
              Max {money(cap)}
            </Button>
          )}
        </div>
        <Button type="submit" variant="primary" size="lg">
          Reveal the question →
        </Button>
      </form>
    </div>
  )
}
