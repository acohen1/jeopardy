/** RulesDialog — turn-order rules for this board. Choices apply instantly
 * (server-authoritative) and the server remembers them as the defaults for
 * every future board. Conditional sections: multi-award transfer only
 * matters under First-correct; first pick only when a mode is automatic. */
import { clsx } from 'clsx'

import { Dialog } from '@/components/ui/Dialog'
import type { Board, FirstPick, MultiAwardRule, TurnMode } from '@/types/board'

export interface RulesDialogProps {
  open: boolean
  board: Board
  onChange: (rules: {
    turn_mode?: TurnMode
    multi_award?: MultiAwardRule
    first_pick?: FirstPick
  }) => void
  onClose: () => void
}

const TURN_MODES: { value: TurnMode; label: string; hint: string }[] = [
  {
    value: 'first-correct',
    label: 'First correct answer',
    hint: 'The classic rule: whoever answers right picks the next clue.',
  },
  {
    value: 'sequential',
    label: 'Take turns',
    hint: 'The board passes around the scoreboard in order, clue by clue.',
  },
  {
    value: 'manual',
    label: 'Host decides',
    hint: 'Hand the board to anyone from the scoreboard; the pick clears after each clue.',
  },
]

const MULTI_AWARD: { value: MultiAwardRule; label: string; hint: string }[] = [
  {
    value: 'first',
    label: 'First award',
    hint: 'The first player awarded keeps the board.',
  },
  {
    value: 'last',
    label: 'Last award',
    hint: 'The most recent award takes the board.',
  },
  {
    value: 'host',
    label: 'Host decides',
    hint: 'Nobody keeps it automatically — hand the board out yourself.',
  },
]

const FIRST_PICK: { value: FirstPick; label: string; hint: string }[] = [
  {
    value: 'random',
    label: 'Random player',
    hint: 'The app picks someone to start.',
  },
  {
    value: 'lowest',
    label: 'Lowest score',
    hint: 'Trailing player starts — great for round two.',
  },
  {
    value: 'host',
    label: 'Host decides',
    hint: 'Nobody starts with the board until you hand it over.',
  },
]

export function RulesDialog({ open, board, onChange, onClose }: RulesDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} title="Game rules" className="w-full max-w-md">
      <div className="max-h-[70vh] space-y-5 overflow-y-auto px-5 py-4">
        <RuleGroup
          idPrefix="rule-turn"
          label="Turn order"
          options={TURN_MODES}
          value={board.turn_mode}
          onSelect={(v) => onChange({ turn_mode: v })}
        />
        {board.turn_mode === 'first-correct' && (
          <RuleGroup
            idPrefix="rule-multi"
            label="When several players score"
            options={MULTI_AWARD}
            value={board.multi_award}
            onSelect={(v) => onChange({ multi_award: v })}
          />
        )}
        {board.turn_mode !== 'manual' && (
          <RuleGroup
            idPrefix="rule-pick"
            label="Who starts"
            options={FIRST_PICK}
            value={board.first_pick}
            onSelect={(v) => onChange({ first_pick: v })}
          />
        )}
        <p className="text-ink-faint text-xs leading-relaxed">
          Changes apply immediately and become the defaults for new boards.
        </p>
      </div>
    </Dialog>
  )
}

function RuleGroup<T extends string>({
  idPrefix,
  label,
  options,
  value,
  onSelect,
}: {
  /** Namespaces the testids — "host" exists in more than one group. */
  idPrefix: string
  label: string
  options: { value: T; label: string; hint: string }[]
  value: T
  onSelect: (value: T) => void
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-ink-muted mb-1.5 text-xs font-semibold tracking-wide uppercase">
        {label}
      </legend>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="radio"
          aria-checked={value === opt.value}
          data-testid={`${idPrefix}-${opt.value}`}
          onClick={() => onSelect(opt.value)}
          className={clsx(
            'block w-full cursor-pointer rounded-xl border px-3.5 py-2.5 text-left transition-colors duration-100',
            value === opt.value
              ? 'border-accent/70 bg-accent/10'
              : 'border-line-soft hover:border-line',
          )}
        >
          <span
            className={clsx(
              'text-sm font-semibold',
              value === opt.value ? 'text-accent' : 'text-ink',
            )}
          >
            {opt.label}
          </span>
          <span className="text-ink-muted mt-0.5 block text-xs leading-relaxed">{opt.hint}</span>
        </button>
      ))}
    </fieldset>
  )
}
