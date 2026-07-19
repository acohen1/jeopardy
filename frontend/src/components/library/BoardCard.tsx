/** One board tile in the library grid. */
import { MoreHorizontal, Play } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import type { BoardSummary } from '@/types/board'

export interface BoardCardProps {
  board: BoardSummary
  onOpen: (board: BoardSummary) => void
  onPlay: (board: BoardSummary) => void
  /** Open the actions menu at viewport coordinates (x, y). */
  onMenu: (board: BoardSummary, x: number, y: number) => void
}

export function BoardCard({ board, onOpen, onPlay, onMenu }: BoardCardProps) {
  const pct =
    board.total_cells > 0 ? Math.round((board.filled_cells / board.total_cells) * 100) : 0
  const updated = new Date(board.updated_at)
  const players = `${board.player_count} ${board.player_count === 1 ? 'player' : 'players'}`

  return (
    <article
      role="button"
      tabIndex={0}
      aria-label={`Open ${board.name}`}
      onClick={() => onOpen(board)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' && e.target === e.currentTarget) onOpen(board)
      }}
      onContextMenu={(e) => {
        e.preventDefault()
        onMenu(board, e.clientX, e.clientY)
      }}
      className="group bg-surface flex cursor-pointer flex-col rounded-xl border border-line-soft p-5 transition-all duration-150 hover:-translate-y-0.5 hover:border-accent hover:shadow-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
    >
      <h2 className="font-display text-ink truncate text-lg font-bold" title={board.name}>
        {board.name}
      </h2>

      <p className="text-ink-muted mt-1 text-[13px]">
        {board.num_cols} × {board.num_rows} · {board.filled_cells}/{board.total_cells} filled ·{' '}
        {players}
      </p>

      <div className="mt-3 h-1 overflow-hidden rounded-full bg-line-soft">
        <div
          className="bg-accent h-full rounded-full transition-[width] duration-150"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-4 flex items-center justify-between gap-2">
        <span className="text-ink-faint text-xs">
          {updated.toLocaleDateString()} ·{' '}
          {updated.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
        </span>
        <div className="flex items-center gap-1.5">
          <Button
            variant="success"
            size="sm"
            onClick={(e) => {
              e.stopPropagation()
              onPlay(board)
            }}
          >
            <Play size={12} fill="currentColor" />
            Play
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Actions for ${board.name}`}
            onClick={(e) => {
              e.stopPropagation()
              const rect = e.currentTarget.getBoundingClientRect()
              onMenu(board, rect.left, rect.bottom + 4)
            }}
          >
            <MoreHorizontal size={15} />
          </Button>
        </div>
      </div>
    </article>
  )
}
