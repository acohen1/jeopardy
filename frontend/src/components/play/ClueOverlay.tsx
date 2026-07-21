/** ClueOverlay — full-screen clue view (question → answer),
 * mirroring legacy CellOverlay:
 *  - QUESTION page award → award + success toast, overlay STAYS OPEN.
 *  - ANSWER page award → award + close.
 *  - Deduct (either page) → negative award + error toast + red button flash,
 *    overlay stays open.
 *  - Hotkeys: A reveal (question), Q back (answer), Esc close — coexist with
 *    SlideView's Space/arrows/R/F.
 * BONUS tiles (fresh opens only — Review passes used:true and skips this):
 * start on a '★ BONUS ★' splash where the host sets a wager; afterwards the
 * question/answer pages behave identically except awards/deducts use the
 * wager and the top badge shows '★ wager'.
 * Only the current page's SlideView is mounted (keyed) so hidden media never
 * plays; closing = unmount, which stops all media. */
import { clsx } from 'clsx'
import { useCallback, useEffect, useRef, useState } from 'react'

import { SlideView } from '@/components/slides/SlideView'
import { Button } from '@/components/ui/Button'
import { toast } from '@/components/ui/Toaster'
import { useHotkeys } from '@/hooks/useHotkeys'
import { money } from '@/lib/format'
import type { Cell, Player } from '@/types/board'

import { BonusSplash } from './BonusSplash'
import { ClueTimer } from './ClueTimer'

export interface ClueOverlayProps {
  boardId: string
  cell: Cell
  players: Player[]
  allowNegatives: boolean
  /** Fires the server-authoritative award mutation. */
  onAward: (name: string, delta: number) => void
  onClose: () => void
}

/** Inline so it reliably beats the variant's utility classes (legacy _flash_button). */
const FLASH_STYLE = {
  background: '#cc2222',
  color: '#ffffff',
  borderColor: '#ff4444',
} as const

export function ClueOverlay({
  boardId,
  cell,
  players,
  allowNegatives,
  onAward,
  onClose,
}: ClueOverlayProps) {
  /* A bonus tile only gets the splash + wager on a FRESH open — the snapshot
   * arrives with used:false exactly then; Review snapshots used:true. */
  const isBonus = cell.bonus && !cell.used
  const [page, setPage] = useState<'bonus' | 'question' | 'answer'>(
    isBonus ? 'bonus' : 'question',
  )
  /* Effective stake for awards/deducts; the tile value until a wager is set. */
  const [wager, setWager] = useState(cell.value)
  const [flashName, setFlashName] = useState<string | null>(null)
  const flashTimer = useRef<number | undefined>(undefined)

  /* Overlay-lifetime memory of user transport-volume drags (keyed by asset
   * path) so a volume set on the question page survives Q↔A remounts. */
  const volumeOverrides = useRef(new Map<string, number>())
  const rememberVolume = useCallback((assetKey: string, volume: number) => {
    volumeOverrides.current.set(assetKey, volume)
  }, [])

  useEffect(() => () => window.clearTimeout(flashTimer.current), [])

  useHotkeys({
    Escape: () => {
      // While a video is fullscreen, Esc only exits fullscreen (natively) —
      // it must not also close the whole overlay.
      if (document.fullscreenElement) return
      onClose()
    },
    // No A/Q navigation on the bonus splash — only Esc (and the wager form).
    ...(page === 'question'
      ? { a: () => setPage('answer') }
      : page === 'answer'
        ? { q: () => setPage('question') }
        : {}),
  })

  /* What an award/deduct is worth: the wager on bonus opens, else tile value. */
  const stake = isBonus ? wager : cell.value

  const award = (name: string) => {
    onAward(name, stake)
    if (page === 'answer') {
      onClose()
    } else {
      toast(`+ ${money(stake)} → ${name}`, { kind: 'success' })
    }
  }

  const deduct = (name: string) => {
    onAward(name, -stake)
    toast(`− ${money(stake)} → ${name}`, { kind: 'error' })
    setFlashName(name)
    window.clearTimeout(flashTimer.current)
    flashTimer.current = window.setTimeout(() => setFlashName(null), 300)
  }

  const slide = page === 'answer' ? cell.answer_slide : cell.question_slide

  return (
    <div className="bg-bg-deep animate-fade-in fixed inset-0 z-40 flex flex-col gap-5 px-12 py-8">
      {/* Top bar — nav flanking the value badge */}
      <div className="grid shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="flex items-center justify-start gap-2">
          {/* Timer lives outside the keyed SlideView so it survives Q↔A flips */}
          <ClueTimer />
          {page === 'answer' && (
            <Button variant="ghost" size="sm" onClick={() => setPage('question')}>
              ← Question
              <Kbd>Q</Kbd>
            </Button>
          )}
        </div>
        {isBonus && page !== 'bonus' ? (
          /* Stakes badge: the host's wager, starred so everyone sees it */
          <div className="text-dollar font-display text-3xl font-bold" title="Bonus wager">
            <span className="mr-1.5 align-[0.2em] text-xl">★</span>
            {money(wager)}
          </div>
        ) : (
          <div className="text-dollar font-display text-3xl font-bold">{money(cell.value)}</div>
        )}
        <div className="flex justify-end">
          {page === 'question' ? (
            <Button variant="ghost" size="sm" onClick={() => setPage('answer')}>
              Reveal answer →<Kbd>A</Kbd>
            </Button>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => onClose()}>
              Close
              <Kbd>Esc</Kbd>
            </Button>
          )}
        </div>
      </div>

      {page === 'bonus' ? (
        /* Bonus splash — wager first; SlideView stays unmounted until reveal */
        <BonusSplash
          tileValue={cell.value}
          onSubmit={(w) => {
            setWager(w)
            setPage('question')
          }}
          onCancel={onClose}
        />
      ) : (
        /* Slide area — only the current page is mounted (key forces remount) */
        <div
          className={clsx(
            'flex min-h-0 flex-1 flex-col rounded-2xl p-4 transition-colors duration-150',
            page === 'answer' && 'bg-answer',
          )}
        >
          <SlideView
            key={page}
            slide={slide}
            boardId={boardId}
            hotkeys
            volumeOverrides={volumeOverrides.current}
            onVolumeChange={rememberVolume}
            className="min-h-0 flex-1"
          />
        </div>
      )}

      {/* Award rows (not while the wager is still being set) */}
      <div className={clsx('shrink-0 space-y-3', page === 'bonus' && 'hidden')}>
        {players.length === 0 ? (
          <p className="text-ink-muted text-center text-sm">
            No players yet — add them in the editor
          </p>
        ) : (
          <>
            <div className="space-y-2">
              <p className="text-ink-muted text-center text-sm">Award points to:</p>
              <div className="flex flex-wrap justify-center gap-2.5">
                {players.map((p) => (
                  <Button key={p.name} variant="success" onClick={() => award(p.name)}>
                    + {p.name}
                  </Button>
                ))}
              </div>
            </div>
            {allowNegatives && (
              <div className="space-y-2">
                <p className="text-ink-muted text-center text-sm">Deduct (wrong answer):</p>
                <div className="flex flex-wrap justify-center gap-2.5">
                  {players.map((p) => (
                    <Button
                      key={p.name}
                      variant="deduct"
                      style={flashName === p.name ? FLASH_STYLE : undefined}
                      onClick={() => deduct(p.name)}
                    >
                      − {p.name}
                    </Button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Kbd({ children }: { children: string }) {
  return (
    <kbd className="text-ink-faint border-line/60 ml-1.5 rounded border px-1.5 py-px font-sans text-[10px]">
      {children}
    </kbd>
  )
}
