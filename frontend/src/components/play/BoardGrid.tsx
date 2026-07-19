/** BoardGrid — category headers + money cells, filling the available space.
 * Unused cells open on left-click; used cells only respond to right-click
 * (Review / Reset cell), mirroring legacy PlayMode._build_board_grid. */
import type { MouseEvent as ReactMouseEvent } from 'react'

import { money } from '@/lib/format'
import type { Board } from '@/types/board'

export interface BoardGridProps {
  board: Board
  /** Left-click on an UNUSED cell. */
  onOpenCell: (row: number, col: number) => void
  /** Right-click on a USED cell (event already default-prevented). */
  onUsedCellMenu: (e: ReactMouseEvent, row: number, col: number) => void
}

export function BoardGrid({ board, onOpenCell, onUsedCellMenu }: BoardGridProps) {
  return (
    <div
      className="grid min-h-0 min-w-0 flex-1 gap-2"
      style={{
        gridTemplateColumns: `repeat(${board.num_cols}, minmax(0, 1fr))`,
        gridTemplateRows: `auto repeat(${board.num_rows}, minmax(0, 1fr))`,
      }}
    >
      {board.categories.slice(0, board.num_cols).map((cat, c) => (
        <div
          key={`cat-${c}`}
          className="bg-cat text-ink border-line-soft font-display flex min-h-14 items-center justify-center rounded-lg border px-2 py-2 text-center text-sm font-bold break-words md:text-base"
        >
          {cat}
        </div>
      ))}

      {board.cells.slice(0, board.num_rows).map((row, r) =>
        row.slice(0, board.num_cols).map((cell, c) =>
          cell.used ? (
            <button
              key={`${r}-${c}`}
              type="button"
              onContextMenu={(e) => {
                e.preventDefault()
                onUsedCellMenu(e, r, c)
              }}
              className="bg-cell-used text-cell-used-ink border-line-soft/60 cursor-default rounded-lg border text-2xl font-bold xl:text-3xl"
            >
              {money(cell.value)}
            </button>
          ) : (
            <button
              key={`${r}-${c}`}
              type="button"
              onClick={() => onOpenCell(r, c)}
              className="bg-cell text-dollar border-line-soft hover:bg-cell-hover hover:border-accent hover:text-accent-bright active:bg-cell-pressed cursor-pointer rounded-lg border text-2xl font-bold transition-colors duration-100 xl:text-3xl"
            >
              {money(cell.value)}
            </button>
          ),
        ),
      )}
    </div>
  )
}
