/** Right sidebar — player roster stored on the board doc (edited locally,
 * autosaved with everything else). Scores live in Play mode. */
import { Plus, X } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/TextInput'
import { toast } from '@/components/ui/Toaster'
import type { Player } from '@/types/board'

export interface PlayerPanelProps {
  players: Player[]
  onAdd: (name: string) => void
  onRemove: (name: string) => void
}

export function PlayerPanel({ players, onAdd, onRemove }: PlayerPanelProps) {
  const [draft, setDraft] = useState('')

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const name = draft.trim()
    if (!name) {
      toast('Enter a player name', { kind: 'error' })
      return
    }
    if (players.some((p) => p.name === name)) {
      toast(`"${name}" is already in the game`, { kind: 'error' })
      return
    }
    onAdd(name)
    setDraft('')
  }

  return (
    <aside className="bg-bg-deep/40 flex w-64 shrink-0 flex-col border-l border-line-soft p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-accent-bright text-sm font-semibold">Players</h2>
        <span className="bg-surface text-ink-muted rounded-full px-2 py-0.5 text-xs tabular-nums">
          {players.length}
        </span>
      </div>

      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto">
        {players.length === 0 ? (
          <p className="text-ink-faint text-sm">No players yet.</p>
        ) : (
          players.map((p) => (
            <div
              key={p.name}
              className="bg-surface flex items-center justify-between gap-2 rounded-lg border border-line-soft px-2.5 py-1.5"
            >
              <span className="text-ink min-w-0 truncate text-sm" title={p.name}>
                {p.name}
              </span>
              <button
                type="button"
                aria-label={`Remove ${p.name}`}
                title={`Remove ${p.name}`}
                onClick={() => onRemove(p.name)}
                className="text-ink-faint hover:bg-cell hover:text-danger shrink-0 cursor-pointer rounded-md p-0.5 transition-colors duration-100"
              >
                <X size={14} />
              </button>
            </div>
          ))
        )}
      </div>

      <form onSubmit={submit} className="mt-3 flex gap-1.5">
        <TextInput
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Player name"
          aria-label="New player name"
          className="min-w-0 flex-1"
        />
        <Button type="submit" variant="success" aria-label="Add player" title="Add player">
          <Plus size={15} />
        </Button>
      </form>

      <p className="text-ink-faint mt-3 text-xs leading-relaxed">
        Scores &amp; negatives are managed in Play mode.
      </p>
    </aside>
  )
}
