/** Scoreboard — right column of live player scores (legacy _build_scoreboard).
 * Host tools: click a score to edit it inline (Enter commits, Esc/blur
 * cancels), a collapsible history feed, and an Undo-last button. */
import { clsx } from 'clsx'
import { Gamepad2, Undo2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'

import { Button } from '@/components/ui/Button'
import { toast } from '@/components/ui/Toaster'
import { money } from '@/lib/format'
import type { Player, ScoreEvent } from '@/types/board'

import { HistoryPanel } from './HistoryPanel'

export interface ScoreboardProps {
  players: Player[]
  history: ScoreEvent[]
  /** Live-session phone presence by player name — absent when not hosting. */
  presence?: ReadonlyMap<string, boolean>
  /** Whose pick it is under the turn rules (highlighted); null = nobody. */
  controlPlayer?: string | null
  /** Hand the board to a player (hover affordance); absent hides it. */
  onGiveControl?: (name: string | null) => void
  onResetScores: () => void
  /** Host correction — commit an absolute score for a player. */
  onSetScore: (name: string, score: number) => void
  /** Reverse the latest history event. */
  onUndo: () => void
}

/** "+$600 → Sakura" / "−$200 → Sakura" / "= $1,000 → Sakura". */
function describeEvent(ev: ScoreEvent): string {
  if (ev.kind === 'set') return `= ${money(ev.after)} → ${ev.player}`
  return `${ev.delta >= 0 ? '+' : '−'}${money(Math.abs(ev.delta))} → ${ev.player}`
}

/** Strip $ , spaces (and unicode minus) → integer, or null when invalid. */
function parseScore(raw: string): number | null {
  const cleaned = raw.replace(/−/g, '-').replace(/[$,\s]/g, '')
  if (!/^-?\d+$/.test(cleaned)) return null
  const n = Number(cleaned)
  return Number.isSafeInteger(n) ? n : null
}

export function Scoreboard({
  players,
  history,
  presence,
  controlPlayer = null,
  onGiveControl,
  onResetScores,
  onSetScore,
  onUndo,
}: ScoreboardProps) {
  // Only one score is editable at a time.
  const [editing, setEditing] = useState<string | null>(null)

  const lastEvent = history.length > 0 ? history[history.length - 1] : null

  const undo = () => {
    if (!lastEvent) return
    // Describe from the last event BEFORE firing — the mutation replaces it.
    toast(`Undid: ${describeEvent(lastEvent)}`, { kind: 'info' })
    onUndo()
  }

  return (
    <aside className="bg-surface border-line-soft flex w-56 shrink-0 flex-col gap-3 rounded-xl border p-4">
      <h2 className="text-accent text-center text-sm font-bold tracking-[0.25em]">SCORES</h2>
      <div className="bg-line-soft h-px shrink-0" />

      <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto">
        {players.length === 0 ? (
          <p className="text-ink-muted px-1 pt-2 text-center text-xs leading-relaxed">
            No players yet — add them in the editor
          </p>
        ) : (
          players.map((p) => (
            <div
              key={p.name}
              className={clsx(
                'group/card shrink-0 rounded-xl border px-3 py-2.5',
                p.name === controlPlayer
                  ? 'border-dollar/60 bg-dollar/10' // whose pick it is
                  : 'bg-surface-warm border-line-soft',
              )}
            >
              <p className="text-ink flex items-center text-sm font-bold break-words">
                {p.name === controlPlayer && (
                  /* Same icon the hand-off button uses: whoever "holds the
                   * gamepad" has the board. */
                  <Gamepad2
                    aria-label="Has the board — their pick"
                    className="text-dollar mr-1.5 size-3.5 shrink-0"
                  >
                    <title>Has the board — their pick</title>
                  </Gamepad2>
                )}
                <span className="min-w-0">{p.name}</span>
                {presence?.get(p.name) && (
                  <span
                    title="Connected on phone"
                    className="bg-accent ml-1.5 inline-block size-1.5 shrink-0 animate-pulse rounded-full"
                  />
                )}
                {onGiveControl && p.name !== controlPlayer && (
                  <button
                    type="button"
                    title={`Give ${p.name} the board`}
                    aria-label={`Give ${p.name} the board`}
                    onClick={() => onGiveControl(p.name)}
                    className="text-ink-faint hover:text-dollar ml-auto cursor-pointer pl-1 opacity-0 transition-opacity duration-100 group-hover/card:opacity-100"
                  >
                    <Gamepad2 className="size-3.5" />
                  </button>
                )}
              </p>
              {editing === p.name ? (
                <ScoreEditor
                  initial={p.score}
                  onCommit={(score) => {
                    onSetScore(p.name, score)
                    setEditing(null)
                  }}
                  onCancel={() => setEditing(null)}
                />
              ) : (
                <button
                  type="button"
                  title="Click to edit"
                  onClick={() => setEditing(p.name)}
                  className={clsx(
                    'block w-full cursor-pointer text-right text-xl font-bold',
                    'decoration-dotted underline-offset-4 hover:underline',
                    p.score >= 0 ? 'text-accent' : 'text-danger',
                  )}
                >
                  {money(p.score)}
                </button>
              )}
            </div>
          ))
        )}
      </div>

      <div className="bg-line-soft h-px shrink-0" />
      <HistoryPanel history={history} />

      <div className="flex shrink-0 flex-col gap-2">
        <Button
          variant="ghost"
          onClick={undo}
          disabled={!lastEvent}
          title={lastEvent ? `Undo: ${describeEvent(lastEvent)}` : 'Nothing to undo'}
        >
          <Undo2 className="size-4" />
          Undo last
        </Button>
        <Button variant="danger" onClick={onResetScores} disabled={players.length === 0}>
          Reset scores
        </Button>
      </div>
    </aside>
  )
}

/** Inline score editor: prefilled raw number, autofocus + select-all.
 * Enter commits (invalid → error toast, stays); Escape or blur cancels. */
function ScoreEditor({
  initial,
  onCommit,
  onCancel,
}: {
  initial: number
  onCommit: (score: number) => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLInputElement>(null)

  useEffect(() => {
    ref.current?.select()
  }, [])

  const onKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const parsed = parseScore(e.currentTarget.value)
      if (parsed === null) {
        toast('Invalid score — enter a whole number', { kind: 'error' })
        e.currentTarget.select()
        return
      }
      onCommit(parsed)
    } else if (e.key === 'Escape') {
      onCancel()
    }
  }

  return (
    <input
      ref={ref}
      autoFocus
      defaultValue={String(initial)}
      inputMode="numeric"
      aria-label="Edit score"
      className={clsx(
        'bg-surface text-ink placeholder:text-ink-faint border-line mt-0.5 w-full rounded-lg border px-2 py-1 text-right text-lg font-bold',
        'focus:border-accent focus:outline-none',
      )}
      onKeyDown={onKeyDown}
      onBlur={onCancel}
    />
  )
}
