/** Editable board grid — category header inputs, row-value inputs, and cell
 * cards. Right-click on a cell offers Copy / Paste / Clear, a bonus-tile
 * toggle (star badge shown only in the editor — secret in play mode), plus
 * "Swap with…" any other row in the same column (slides move, values stay —
 * legacy parity). */
import { Star } from 'lucide-react'
import { Fragment, useEffect, useState } from 'react'

import {
  getClipboardCell,
  hasClipboardCell,
  setClipboardCell,
} from '@/components/editor/cellClipboard'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ContextMenu } from '@/components/ui/ContextMenu'
import type { ContextMenuItem, ContextMenuState } from '@/components/ui/ContextMenu'
import { toast } from '@/components/ui/Toaster'
import { money, truncate } from '@/lib/format'
import { emptySlide } from '@/types/board'
import type { Board, Cell } from '@/types/board'

export interface BoardGridProps {
  board: Board
  onUpdate: (updater: (b: Board) => Board) => void
  onEditCell: (row: number, col: number) => void
}

export function BoardGrid({ board, onUpdate, onEditCell }: BoardGridProps) {
  const [menu, setMenu] = useState<ContextMenuState | null>(null)
  const [clearing, setClearing] = useState<{ row: number; col: number } | null>(null)

  const setCategory = (col: number, text: string) =>
    onUpdate((b) => ({
      ...b,
      categories: b.categories.map((cat, i) => (i === col ? text : cat)),
    }))

  // Legacy parity: a row-value change sets row_values[r] AND every cell in
  // that row's value.
  const setRowValue = (row: number, value: number) =>
    onUpdate((b) => ({
      ...b,
      row_values: b.row_values.map((v, i) => (i === row ? value : v)),
      cells: b.cells.map((r, ri) => (ri === row ? r.map((cell) => ({ ...cell, value })) : r)),
    }))

  const swapCells = (rowA: number, rowB: number, col: number) =>
    onUpdate((b) => {
      const cells = b.cells.map((r) => [...r])
      const a = cells[rowA][col]
      const c = cells[rowB][col]
      cells[rowA][col] = { ...a, question_slide: c.question_slide, answer_slide: c.answer_slide }
      cells[rowB][col] = { ...c, question_slide: a.question_slide, answer_slide: a.answer_slide }
      return { ...b, cells }
    })

  const copyCell = (row: number, col: number) => {
    const cell = board.cells[row][col]
    setClipboardCell(cell.question_slide, cell.answer_slide, board.id)
    toast('Cell copied', { kind: 'info' })
  }

  // Same rule as swap: slides replace, value and used stay untouched.
  const pasteCell = (row: number, col: number) => {
    const clip = getClipboardCell()
    if (!clip) return
    onUpdate((b) => {
      const cells = b.cells.map((r) => [...r])
      cells[row][col] = {
        ...cells[row][col],
        question_slide: clip.question_slide,
        answer_slide: clip.answer_slide,
      }
      return { ...b, cells }
    })
    toast('Cell pasted', { kind: 'info' })
    if (clip.sourceBoardId !== board.id) {
      toast('Copied from another board — its media files may be missing here', {
        kind: 'info',
        duration: 3500,
      })
    }
  }

  const clearCell = (row: number, col: number) => {
    onUpdate((b) => {
      const cells = b.cells.map((r) => [...r])
      cells[row][col] = {
        ...cells[row][col],
        question_slide: emptySlide(),
        answer_slide: emptySlide(),
      }
      return { ...b, cells }
    })
    toast('Cell cleared', { kind: 'info' })
  }

  // Bonus tiles look identical to normal ones on the play board — the star
  // only ever shows here, in the editor.
  const toggleBonus = (row: number, col: number) => {
    const marking = !board.cells[row][col].bonus
    onUpdate((b) => {
      const cells = b.cells.map((r) => [...r])
      cells[row][col] = { ...cells[row][col], bonus: !cells[row][col].bonus }
      return { ...b, cells }
    })
    toast(marking ? 'Bonus tile set — it stays secret in play mode' : 'Bonus removed', {
      kind: 'info',
    })
  }

  const openMenu = (e: React.MouseEvent, row: number, col: number) => {
    e.preventDefault()
    const items: ContextMenuItem[] = [
      { label: 'Copy cell', onSelect: () => copyCell(row, col) },
      {
        label: 'Paste cell',
        onSelect: () => pasteCell(row, col),
        disabled: !hasClipboardCell(),
      },
      { label: 'Clear cell…', danger: true, onSelect: () => setClearing({ row, col }) },
      {
        label: board.cells[row][col].bonus ? 'Remove bonus ★' : 'Mark as bonus ★',
        onSelect: () => toggleBonus(row, col),
      },
      { type: 'separator' },
      { type: 'heading', label: 'Swap with…' },
    ]
    if (board.num_rows <= 1) {
      items.push({ label: 'No other rows', onSelect: () => undefined, disabled: true })
    } else {
      for (let r = 0; r < board.num_rows; r++) {
        if (r === row) continue
        const other = r
        items.push({
          label: `Row ${r + 1} · ${money(board.cells[r][col].value)}`,
          onSelect: () => swapCells(row, other, col),
        })
      }
    }
    setMenu({ x: e.clientX, y: e.clientY, items })
  }

  return (
    <>
      <div
        className="grid min-w-fit gap-2"
        style={{ gridTemplateColumns: `88px repeat(${board.num_cols}, minmax(150px, 1fr))` }}
      >
        {/* Corner placeholder above the value column */}
        <div aria-hidden />

        {board.categories.slice(0, board.num_cols).map((cat, c) => (
          <input
            key={`cat-${c}`}
            value={cat}
            onChange={(e) => setCategory(c, e.target.value)}
            placeholder={`Category ${c + 1}`}
            aria-label={`Category ${c + 1} name`}
            className="bg-surface-warm text-ink placeholder:text-ink-faint focus:border-accent rounded-lg border border-line-soft px-2 py-2.5 text-center text-sm font-bold transition-colors duration-100 focus:outline-none"
          />
        ))}

        {board.cells.slice(0, board.num_rows).map((row, r) => (
          <Fragment key={`row-${r}`}>
            <RowValueInput value={board.row_values[r]} onCommit={(v) => setRowValue(r, v)} />
            {row.slice(0, board.num_cols).map((cell, c) => (
              <CellCard
                key={`cell-${r}-${c}`}
                cell={cell}
                onOpen={() => onEditCell(r, c)}
                onContextMenu={(e) => openMenu(e, r, c)}
              />
            ))}
          </Fragment>
        ))}
      </div>

      <ContextMenu state={menu} onClose={() => setMenu(null)} />

      <ConfirmDialog
        open={clearing !== null}
        title="Clear cell"
        message="Remove this cell's question and answer content?"
        confirmLabel="Clear"
        danger
        onConfirm={() => {
          if (clearing) clearCell(clearing.row, clearing.col)
          setClearing(null)
        }}
        onCancel={() => setClearing(null)}
      />
    </>
  )
}

/** '$400'-style input; parses by stripping $/commas, reverting when invalid. */
function RowValueInput({ value, onCommit }: { value: number; onCommit: (v: number) => void }) {
  const [text, setText] = useState(() => money(value))

  useEffect(() => {
    setText(money(value))
  }, [value])

  const commit = () => {
    const clean = text.replace(/[$,\s]/g, '')
    if (/^-?\d+$/.test(clean)) {
      const parsed = parseInt(clean, 10)
      onCommit(parsed)
      setText(money(parsed))
    } else {
      setText(money(value))
    }
  }

  return (
    <input
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur()
      }}
      aria-label="Row value"
      className="bg-surface-warm text-dollar focus:border-accent w-full rounded-lg border border-line-soft px-2 py-2 text-center text-sm font-bold transition-colors duration-100 focus:outline-none"
    />
  )
}

function CellCard({
  cell,
  onOpen,
  onContextMenu,
}: {
  cell: Cell
  onOpen: () => void
  onContextMenu: (e: React.MouseEvent) => void
}) {
  const question = cell.question_slide.text.trim()
  const totalAssets = cell.question_slide.assets.length + cell.answer_slide.assets.length

  return (
    <button
      type="button"
      onClick={onOpen}
      onContextMenu={onContextMenu}
      className="bg-surface hover:border-accent active:bg-cell-pressed relative flex min-h-16 cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-line-soft px-2 py-2 text-center transition-colors duration-100"
    >
      {cell.bonus && (
        <span
          title="Bonus tile — secret in play mode"
          className="absolute top-1.5 right-1.5"
        >
          <Star size={12} className="text-dollar" fill="currentColor" />
        </span>
      )}
      {question ? (
        <span className="text-ink text-sm font-semibold">{truncate(question, 28)}</span>
      ) : (
        totalAssets === 0 && <span className="text-ink-faint text-sm">(empty)</span>
      )}
      {totalAssets > 0 && (
        <span className="bg-cell text-ink-muted rounded-full px-2 py-0.5 text-[11px]">
          {totalAssets} asset{totalAssets === 1 ? '' : 's'}
        </span>
      )}
    </button>
  )
}
