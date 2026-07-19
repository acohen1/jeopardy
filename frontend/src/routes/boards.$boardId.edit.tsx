import { useSuspenseQuery } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'

import { boardQuery } from '@/api/boards'
import { BoardGrid } from '@/components/editor/BoardGrid'
import { CellEditorDialog } from '@/components/editor/CellEditorDialog'
import { EditorToolbar } from '@/components/editor/EditorToolbar'
import { PlayerPanel } from '@/components/editor/PlayerPanel'
import { useBoardDraft } from '@/components/editor/useBoardDraft'
import { toast } from '@/components/ui/Toaster'
import { usePageTitle } from '@/hooks/usePageTitle'
import { money, truncate } from '@/lib/format'
import { resizeBoard } from '@/types/board'
import type { Board, Cell, Slide } from '@/types/board'

export const Route = createFileRoute('/boards/$boardId/edit')({
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(boardQuery(params.boardId)),
  component: EditPage,
})

function EditPage() {
  const { boardId } = Route.useParams()
  const { data } = useSuspenseQuery(boardQuery(boardId))
  // key: a fresh working copy per board — later cache updates never clobber
  // in-progress local edits.
  return <Editor key={boardId} initial={data} />
}

function Editor({ initial }: { initial: Board }) {
  const navigate = useNavigate()
  const { board, status, update, flush } = useBoardDraft(initial)
  const [editing, setEditing] = useState<{ row: number; col: number } | null>(null)
  usePageTitle(`${board.name} · Edit — Chaewon Jeopardy`)

  // Ctrl/Cmd+S — flush the debounced autosave right now. useHotkeys skips all
  // ctrl/meta chords by design, so this needs its own window listener; it lives
  // in the Editor component so it only fires on the edit page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return
      if (e.key !== 's' && e.key !== 'S') return
      e.preventDefault() // always block the browser's save dialog
      if (e.repeat) return
      void flush().then((clean) => {
        // On failure (clean === false) useBoardDraft already raised its
        // 'Autosave failed' error toast — don't stack a second one.
        if (clean) toast('Saved', { kind: 'success' })
      })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [flush])

  // In-session "max-extent" stash of everything a shrink has trimmed —
  // resizeBoard drops out-of-range cells/categories/values and autosave
  // persists the trimmed doc, so shrinking then re-growing must restore the
  // content from here for a lossless '-' → '+' round-trip.
  const trimStashRef = useRef<{
    categories: string[]
    rowValues: number[]
    cells: Map<string, Cell>
  }>({ categories: [], rowValues: [], cells: new Map() })

  const onResize = (rows: number, cols: number) => {
    update((b) => {
      const stash = trimStashRef.current
      // Merge the CURRENT extent into the stash (latest content wins).
      b.categories.forEach((cat, i) => {
        stash.categories[i] = cat
      })
      b.row_values.forEach((v, i) => {
        stash.rowValues[i] = v
      })
      b.cells.forEach((row, r) => {
        row.forEach((cell, c) => stash.cells.set(`${r}:${c}`, cell))
      })

      const next = resizeBoard(b, rows, cols)
      // Slots beyond the pre-resize extent were padded with defaults —
      // restore the stashed originals where we have them.
      const categories = next.categories.map((cat, i) =>
        i < b.num_cols ? cat : (stash.categories[i] ?? cat),
      )
      const row_values = next.row_values.map((v, i) =>
        i < b.num_rows ? v : (stash.rowValues[i] ?? v),
      )
      const cells = next.cells.map((row, r) =>
        row.map((cell, c) =>
          r < b.num_rows && c < b.num_cols ? cell : (stash.cells.get(`${r}:${c}`) ?? cell),
        ),
      )
      return { ...next, categories, row_values, cells }
    })
  }

  const onPlay = () => {
    if (board.players.length === 0) {
      toast('Add at least one player before starting', { kind: 'error' })
      return
    }
    void flush().then((clean) => {
      if (clean) {
        void navigate({ to: '/boards/$boardId/play', params: { boardId: board.id } })
      }
    })
  }

  const commitCell = (row: number, col: number, question: Slide, answer: Slide) => {
    update((b) => {
      const cells = b.cells.map((r) => [...r])
      cells[row][col] = { ...cells[row][col], question_slide: question, answer_slide: answer }
      return { ...b, cells }
    })
    setEditing(null)
  }

  const editingCell = editing ? board.cells[editing.row][editing.col] : null

  return (
    <main className="flex h-dvh min-h-0 flex-col">
      <EditorToolbar
        name={board.name}
        numRows={board.num_rows}
        numCols={board.num_cols}
        status={status}
        onRename={(name) => update((b) => ({ ...b, name }))}
        onResize={onResize}
        onPlay={onPlay}
      />

      <div className="flex min-h-0 flex-1">
        <div className="min-h-0 flex-1 overflow-auto p-4">
          <BoardGrid
            board={board}
            onUpdate={update}
            onEditCell={(row, col) => setEditing({ row, col })}
          />
        </div>
        <PlayerPanel
          players={board.players}
          onAdd={(name) => update((b) => ({ ...b, players: [...b.players, { name, score: 0 }] }))}
          onRemove={(name) =>
            update((b) => ({ ...b, players: b.players.filter((p) => p.name !== name) }))
          }
        />
      </div>

      {editing && editingCell && (
        <CellEditorDialog
          key={`${editing.row}-${editing.col}`}
          cell={editingCell}
          boardId={board.id}
          title={`${truncate(board.categories[editing.col]?.trim() || `Category ${editing.col + 1}`, 24)} · ${money(editingCell.value)}`}
          onSave={(q, a) => commitCell(editing.row, editing.col, q, a)}
          onCancel={() => setEditing(null)}
        />
      )}
    </main>
  )
}
