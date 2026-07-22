/** ClueOverlay — full-screen clue view (question → answer),
 * mirroring legacy CellOverlay:
 *  - QUESTION page award → award + success toast, overlay STAYS OPEN.
 *  - ANSWER page award → award + close.
 *  - Deduct (either page) → negative award + error toast + red button flash,
 *    overlay stays open.
 *  - Hotkeys: A reveal (question), Q back (answer), Esc close — coexist with
 *    SlideView's Space/arrows/R/F. Hosted games add C/W to resolve a buzz.
 * BONUS tiles (fresh opens only — Review passes used:true and skips this):
 * start on a '★ BONUS ★' splash where the host sets a wager; afterwards the
 * question/answer pages behave identically except awards/deducts use the
 * wager and the top badge shows '★ wager'.
 * Only the current page's SlideView is mounted (keyed) so hidden media never
 * plays; closing = unmount, which stops all media. */
import { clsx } from 'clsx'
import { Zap } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { SlideView } from '@/components/slides/SlideView'
import { Button } from '@/components/ui/Button'
import { toast } from '@/components/ui/Toaster'
import { useHotkeys } from '@/hooks/useHotkeys'
import { money } from '@/lib/format'
import type { BuzzerState, HostCommand } from '@/lib/live'
import { playSfx } from '@/lib/sfx'
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
  /** Live buzzer state while a hosted session is active — null/absent hides
   * every buzzer surface (zero behavior change without a session). */
  buzzer?: BuzzerState | null
  /** Sends a host command over the live socket (present iff hosting). */
  onBuzzerCommand?: (command: HostCommand) => void
  /* ---- Turn rules (control transfers are decided by PlayMode when the
   * clue CLOSES, from the awards made during it — not here) ---- */
  controlPlayer?: string | null
  /** Highest row value — the Daily Double wager floor. */
  topRowValue?: number
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
  buzzer,
  onBuzzerCommand,
  controlPlayer = null,
  topRowValue = 0,
}: ClueOverlayProps) {
  /* A bonus tile only gets the splash + wager on a FRESH open — the snapshot
   * arrives with used:false exactly then; Review snapshots used:true. */
  const isBonus = cell.bonus && !cell.used
  const [page, setPage] = useState<'bonus' | 'question' | 'answer'>(
    isBonus ? 'bonus' : 'question',
  )
  /* Effective stake for awards/deducts; the tile value until a wager is set. */
  const [wager, setWager] = useState(cell.value)
  /* Who the bonus wager belongs to (chosen on the splash). */
  const [wagerer, setWagerer] = useState<string | null>(null)
  const [flashName, setFlashName] = useState<string | null>(null)
  const flashTimer = useRef<number | undefined>(undefined)

  /* Overlay-lifetime memory of user transport-volume drags (keyed by asset
   * path) so a volume set on the question page survives Q↔A remounts. */
  const volumeOverrides = useRef(new Map<string, number>())
  const rememberVolume = useCallback((assetKey: string, volume: number) => {
    volumeOverrides.current.set(assetKey, volume)
  }, [])

  useEffect(() => () => window.clearTimeout(flashTimer.current), [])

  /* Browsers exit fullscreen on Esc BEFORE (or without) delivering the
   * keydown — so in Present mode one press would exit fullscreen AND close
   * the overlay. Remember when fullscreen last ended and swallow the Esc
   * that caused it; the next press closes the overlay as usual. */
  const lastFsExitRef = useRef(0)
  useEffect(() => {
    const onFsChange = () => {
      if (!document.fullscreenElement) lastFsExitRef.current = Date.now()
    }
    document.addEventListener('fullscreenchange', onFsChange)
    return () => document.removeEventListener('fullscreenchange', onFsChange)
  }, [])

  /* ---- Hosted-session buzzers (no-ops entirely when not hosting) ---- */
  const hosting = buzzer != null && onBuzzerCommand != null

  // Chime once per winner — a fresh 'won' snapshot (or a new winner after a
  // re-arm) means someone just buzzed in.
  const lastWinnerRef = useRef<string | null>(null)
  useEffect(() => {
    if (buzzer?.phase === 'won') {
      if (buzzer.winner !== lastWinnerRef.current) {
        lastWinnerRef.current = buzzer.winner
        playSfx('correct')
      }
    } else {
      lastWinnerRef.current = null
    }
  }, [buzzer])

  // Cleanup on close: leave the buzzer locked so the next clue starts fresh.
  // Refs so the unmount-only effect sees the latest state without re-running.
  const buzzerRef = useRef(buzzer)
  buzzerRef.current = buzzer
  const commandRef = useRef(onBuzzerCommand)
  commandRef.current = onBuzzerCommand
  useEffect(
    () => () => {
      if (buzzerRef.current && buzzerRef.current.phase !== 'locked') {
        commandRef.current?.('reset-buzzer')
      }
    },
    [],
  )

  useHotkeys({
    Escape: () => {
      // While a video is fullscreen, Esc only exits fullscreen (natively) —
      // it must not also close the whole overlay.
      if (document.fullscreenElement) return
      // ...and the Esc that just ENDED fullscreen (Present mode) is spent.
      if (Date.now() - lastFsExitRef.current < 500) return
      onClose()
    },
    // No A/Q navigation on the bonus splash — only Esc (and the wager form).
    ...(page === 'question'
      ? { a: () => setPage('answer') }
      : page === 'answer'
        ? { q: () => setPage('question') }
        : {}),
    // 'B' arms (or re-arms past a wrong winner) — hosted games, Q/A pages only.
    ...(hosting && page !== 'bonus'
      ? {
          b: () => {
            if (buzzer.phase === 'locked') onBuzzerCommand('arm')
            else if (buzzer.phase === 'won') onBuzzerCommand('rearm-excluding-winner')
          },
        }
      : {}),
    // One-key buzz resolution — mirrors the BuzzerStrip's Correct/Wrong buttons.
    ...(hosting && page !== 'bonus' && buzzer.phase === 'won'
      ? {
          c: () => resolveCorrect(buzzer.winner),
          w: () => resolveWrong(buzzer.winner),
        }
      : {}),
  })

  /* What an award/deduct is worth: the wager on bonus opens, else tile value. */
  const stake = isBonus ? wager : cell.value

  const award = (name: string) => {
    playSfx('correct')
    onAward(name, stake)
    if (page === 'answer') {
      onClose()
    } else {
      toast(`+ ${money(stake)} → ${name}`, { kind: 'success' })
    }
  }

  const deduct = (name: string) => {
    playSfx('wrong')
    onAward(name, -stake)
    toast(`− ${money(stake)} → ${name}`, { kind: 'error' })
    setFlashName(name)
    window.clearTimeout(flashTimer.current)
    flashTimer.current = window.setTimeout(() => setFlashName(null), 300)
  }

  /** Buzz-winner got it right: resolve the buzzer FIRST so the phase leaves
   * 'won' immediately (C/W unbind, the strip clears) — on the question page
   * award() keeps the overlay open, so without the reset a second press
   * would double-award. */
  const resolveCorrect = (winner: string) => {
    onBuzzerCommand?.('reset-buzzer')
    award(winner)
  }

  /** Buzz-winner got it wrong: deduct (only when negatives are on), then
   * ALWAYS re-open the buzzers for everyone else so they can steal. */
  const resolveWrong = (winner: string) => {
    if (allowNegatives) deduct(winner)
    onBuzzerCommand?.('rearm-excluding-winner')
  }

  const slide = page === 'answer' ? cell.answer_slide : cell.question_slide

  return (
    <div className="bg-bg-deep animate-fade-in fixed inset-0 z-40 flex flex-col gap-5 px-12 py-8">
      {/* Top bar — nav flanking the value badge */}
      <div className="grid shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="flex items-center justify-start gap-2">
          {/* Timer lives outside the keyed SlideView so it survives Q↔A flips */}
          <ClueTimer />
          {hosting && page !== 'bonus' && (
            <BuzzerStrip
              buzzer={buzzer}
              command={onBuzzerCommand}
              stake={stake}
              allowNegatives={allowNegatives}
              onCorrect={resolveCorrect}
              onWrong={resolveWrong}
            />
          )}
          {page === 'answer' && (
            <Button variant="ghost" size="sm" onClick={() => setPage('question')}>
              ← Question
              <Kbd>Q</Kbd>
            </Button>
          )}
        </div>
        {isBonus && page !== 'bonus' ? (
          /* Stakes badge: the wager + whose neck it's on */
          <div className="text-dollar font-display text-3xl font-bold" title="Bonus wager">
            <span className="mr-1.5 align-[0.2em] text-xl">★</span>
            {money(wager)}
            {wagerer && (
              <span className="text-ink-muted ml-2 align-[0.12em] font-sans text-base font-normal">
                {wagerer}
              </span>
            )}
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
          topRowValue={topRowValue}
          players={players}
          initialWagerer={controlPlayer}
          onSubmit={(w, who) => {
            setWager(w)
            setWagerer(who)
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

/** Host-side buzzer controls for a hosted session — locked → arm button,
 * armed → pulsing chip + disarm, won → winner banner with one-click
 * Correct/Wrong resolution (C/W hotkeys) plus a ghost Reset. */
function BuzzerStrip({
  buzzer,
  command,
  stake,
  allowNegatives,
  onCorrect,
  onWrong,
}: {
  buzzer: BuzzerState
  command: (command: HostCommand) => void
  /** What a resolution is worth — the wager on bonus opens, else tile value. */
  stake: number
  allowNegatives: boolean
  onCorrect: (winner: string) => void
  onWrong: (winner: string) => void
}) {
  if (buzzer.phase === 'locked') {
    return (
      <Button variant="primary" size="sm" onClick={() => command('arm')} title="Arm buzzers [B]">
        <Zap className="size-3.5" />
        Arm buzzers
        <Kbd>B</Kbd>
      </Button>
    )
  }

  if (buzzer.phase === 'armed') {
    return (
      <div className="flex items-center gap-2">
        <span className="border-accent/60 bg-accent/15 text-accent inline-flex animate-pulse items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold">
          <Zap className="size-3.5" />
          Buzzers armed
          {buzzer.lockedOut.length > 0 && (
            <span className="text-ink-muted font-normal">
              · {buzzer.lockedOut.length} locked out
            </span>
          )}
        </span>
        <Button variant="ghost" size="sm" onClick={() => command('disarm')}>
          Disarm
        </Button>
      </div>
    )
  }

  /* won — the winner takes over the strip */
  return (
    <div className="border-accent/50 bg-accent/15 animate-scale-in flex min-w-0 items-center gap-3 rounded-xl border px-3 py-1.5">
      <div className="min-w-0">
        <p className="text-accent-bright truncate text-sm font-bold">
          ⚡ {buzzer.winner} buzzed in!
        </p>
        {buzzer.order.length > 1 && (
          <p className="text-ink-muted truncate text-[11px]">
            also: {buzzer.order.slice(1).join(', ')}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Button
          variant="success"
          size="sm"
          onClick={() => onCorrect(buzzer.winner)}
          title={`Correct — award ${money(stake)} [C]`}
        >
          ✓ Correct +{money(stake)}
        </Button>
        <Button
          variant="deduct"
          size="sm"
          onClick={() => onWrong(buzzer.winner)}
          title={
            allowNegatives
              ? `Wrong — deduct ${money(stake)}, re-arm for everyone else [W]`
              : 'Wrong — re-arm for everyone else [W]'
          }
        >
          {allowNegatives ? <>✗ Wrong −{money(stake)}</> : '✗ Wrong'}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => command('reset-buzzer')}>
          Reset
        </Button>
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
