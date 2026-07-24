import { useSuspenseQuery } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'

import { boardQuery, useGameActions } from '@/api/boards'
import { BoardGrid } from '@/components/editor/BoardGrid'
import { CellEditorDialog } from '@/components/editor/CellEditorDialog'
import { EditorToolbar } from '@/components/editor/EditorToolbar'
import { PlayerPanel } from '@/components/editor/PlayerPanel'
import { useBoardDraft } from '@/components/editor/useBoardDraft'
import { RulesDialog } from '@/components/play/RulesDialog'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { toast } from '@/components/ui/Toaster'
import { usePageTitle } from '@/hooks/usePageTitle'
import { money, truncate } from '@/lib/format'
import { anyModalOpen } from '@/lib/modalState'
import { cellMissingAnswer, resizeBoard } from '@/types/board'
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
  const { board, status, update, flush, undo, redo, canUndo, canRedo } = useBoardDraft(initial)
  const [editing, setEditing] = useState<{ row: number; col: number } | null>(null)
  // Non-null while the "some cells have no answer" pre-play warning is up.
  const [playWarning, setPlayWarning] = useState<string | null>(null)
  // Game rules are PLAY-mode state (the draft's autosave can't touch them by
  // design) — read the live query cache and mutate via the settings endpoint.
  const { data: liveBoard } = useSuspenseQuery(boardQuery(board.id))
  const gameActions = useGameActions(board.id)
  const [rulesOpen, setRulesOpen] = useState(false)
  usePageTitle(`${board.name} · Edit — Rhubarb`)

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

  // Ctrl/Cmd+Z → undo, Ctrl+Y / Ctrl+Shift+Z → redo. Another ctrl/meta chord,
  // so again a bare window listener (useHotkeys skips chords by design).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return
      const key = e.key.toLowerCase()
      const isUndo = key === 'z' && !e.shiftKey
      const isRedo = key === 'y' || (key === 'z' && e.shiftKey)
      if (!isUndo && !isRedo) return
      // While a dialog is open, undo belongs to the dialog's own fields.
      if (anyModalOpen()) return
      // In an input/textarea/contenteditable the native TEXT undo must win.
      const t = e.target
      if (
        t instanceof HTMLElement &&
        (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
      )
        return
      e.preventDefault()
      if (isUndo) undo()
      else redo()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [undo, redo])

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

  const startPlay = () => {
    void flush().then((clean) => {
      if (clean) {
        void navigate({ to: '/boards/$boardId/play', params: { boardId: board.id } })
      }
    })
  }

  const onPlay = () => {
    // No player gate: play mode opens as a LOBBY — friends join from their
    // phones there, and the board itself is gated behind Start game.
    // Readiness check: cells with a question but no answer would be discovered
    // live at game night — warn (but don't block) before starting.
    const incomplete: string[] = []
    board.cells.slice(0, board.num_rows).forEach((row) => {
      row.slice(0, board.num_cols).forEach((cell, c) => {
        if (cellMissingAnswer(cell)) {
          const cat = board.categories[c]?.trim() || `Category ${c + 1}`
          incomplete.push(`${truncate(cat, 24)} · ${money(cell.value)}`)
        }
      })
    })
    if (incomplete.length > 0) {
      const shown = incomplete.slice(0, 5).join(', ')
      const more = incomplete.length > 5 ? ` +${incomplete.length - 5} more` : ''
      setPlayWarning(
        `These cells have a question but no answer yet: ${shown}${more}.`,
      )
      return
    }
    startPlay()
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
        canUndo={canUndo}
        canRedo={canRedo}
        onUndo={undo}
        onRedo={redo}
        onRename={(name) => update((b) => ({ ...b, name }))}
        onResize={onResize}
        onRules={() => setRulesOpen(true)}
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

      <RulesDialog
        open={rulesOpen}
        board={liveBoard}
        onChange={(rules) => gameActions.setRules.mutate([rules])}
        onClose={() => setRulesOpen(false)}
      />

      <ConfirmDialog
        open={playWarning !== null}
        title="Some cells have no answer"
        message={playWarning ?? ''}
        confirmLabel="Play anyway"
        onConfirm={() => {
          setPlayWarning(null)
          startPlay()
        }}
        onCancel={() => setPlayWarning(null)}
      />

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
