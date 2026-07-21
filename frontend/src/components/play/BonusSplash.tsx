/** BonusSplash — the "★ BONUS ★" reveal page shown when a bonus (Daily
 * Double) tile is opened fresh. The host sets a wager (defaults to the tile
 * value, with quick chips for 1× and 2×) and then reveals the question.
 * Purely presentational: parses/validates the wager and hands the number up. */
import { useState } from 'react'
import type { FormEvent, KeyboardEvent as ReactKeyboardEvent } from 'react'

import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/TextInput'
import { toast } from '@/components/ui/Toaster'
import { money } from '@/lib/format'

export interface BonusSplashProps {
  /** The tile's printed value — the wager default and the base for the chips. */
  tileValue: number
  /** Called with the validated wager when the host reveals the question. */
  onSubmit: (wager: number) => void
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

export function BonusSplash({ tileValue, onSubmit, onCancel }: BonusSplashProps) {
  const [raw, setRaw] = useState(String(tileValue))

  const setFromChip = (amount: number) => {
    setRaw(String(amount))
    // Keep the field ready for an immediate Enter / manual tweak.
    requestAnimationFrame(focusWagerInput)
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const wager = parseWager(raw)
    if (!Number.isFinite(wager) || wager <= 0) {
      toast('Enter a positive wager', { kind: 'error' })
      focusWagerInput()
      return
    }
    onSubmit(wager)
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
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-10">
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

      <form onSubmit={submit} className="flex flex-col items-center gap-7">
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
        </div>
        <Button type="submit" variant="primary" size="lg">
          Reveal the question →
        </Button>
      </form>
    </div>
  )
}
