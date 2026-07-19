/** Board library — the home page: hero header, board grid, and all
 * library-level operations (create / rename / duplicate / export / delete / import). */
import { useMutation, useQueryClient, useSuspenseQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Plus, Upload } from 'lucide-react'
import { useRef, useState } from 'react'

import {
  boardsQuery,
  createBoard,
  deleteBoard,
  duplicateBoard,
  exportBoardUrl,
  importBoard,
  renameBoard,
} from '@/api/boards'
import { ApiError } from '@/api/client'
import { VersionChip } from '@/components/desktop/AboutDialog'
import { SettingsButton } from '@/components/desktop/SettingsDialog'
import { UpdatePill } from '@/components/desktop/UpdatePill'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ContextMenu, type ContextMenuState } from '@/components/ui/ContextMenu'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toaster'
import type { BoardSummary } from '@/types/board'

import { BoardCard } from './BoardCard'
import { NameDialog } from './NameDialog'

function errorToast(err: unknown) {
  toast(err instanceof ApiError ? err.message : 'Something went wrong', {
    kind: 'error',
    duration: 4000,
  })
}

/** Fire a browser download of the board's export zip (no fetch involved). */
function downloadExport(boardId: string) {
  const a = document.createElement('a')
  a.href = exportBoardUrl(boardId)
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export function LibraryPage() {
  const { data: boards } = useSuspenseQuery(boardsQuery())
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [renaming, setRenaming] = useState<BoardSummary | null>(null)
  const [deleting, setDeleting] = useState<BoardSummary | null>(null)
  const [menu, setMenu] = useState<ContextMenuState | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['boards'] })

  const createMut = useMutation({
    mutationFn: (name: string) => createBoard(name),
    onSuccess: (board) => {
      invalidate()
      navigate({ to: '/boards/$boardId/edit', params: { boardId: board.id } })
    },
    onError: errorToast,
  })

  const renameMut = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => renameBoard(id, name),
    onSuccess: () => {
      invalidate()
      setRenaming(null)
    },
    onError: errorToast,
  })

  const duplicateMut = useMutation({
    mutationFn: (board: BoardSummary) => duplicateBoard(board.id),
    onSuccess: (copy) => {
      invalidate()
      toast(`Duplicated as “${copy.name}”`, { kind: 'success' })
    },
    onError: errorToast,
  })

  const deleteMut = useMutation({
    mutationFn: (board: BoardSummary) => deleteBoard(board.id),
    onSuccess: () => {
      invalidate()
      setDeleting(null)
    },
    onError: errorToast,
  })

  const importMut = useMutation({
    mutationFn: (file: File) => importBoard(file),
    onSuccess: (board) => {
      invalidate()
      toast(`Imported ${board.name}`, { kind: 'success' })
    },
    onError: errorToast,
  })

  const openBoard = (board: BoardSummary) =>
    navigate({ to: '/boards/$boardId/edit', params: { boardId: board.id } })

  const playBoard = (board: BoardSummary) =>
    navigate({ to: '/boards/$boardId/play', params: { boardId: board.id } })

  const openMenu = (board: BoardSummary, x: number, y: number) =>
    setMenu({
      x,
      y,
      items: [
        { label: 'Rename…', onSelect: () => setRenaming(board) },
        { label: 'Duplicate', onSelect: () => duplicateMut.mutate(board) },
        { label: 'Export', onSelect: () => downloadExport(board.id) },
        { type: 'separator' },
        { label: 'Delete…', danger: true, onSelect: () => setDeleting(board) },
      ],
    })

  const pickImportFile = () => fileRef.current?.click()

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">
      {/* ---- Hero header -------------------------------------------- */}
      <header className="flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
        <div>
          <h1 className="font-display text-3xl leading-none font-black tracking-[0.16em] uppercase sm:text-4xl">
            <span className="text-ink">Chaewon</span>{' '}
            <span className="text-accent">Jeopardy</span>
          </h1>
          <div className="via-accent/60 mt-3 h-px w-full max-w-105 bg-gradient-to-r from-accent to-transparent" />
          <p className="text-ink-muted mt-2.5 text-sm tracking-wide">
            Build the board. Run the show.
          </p>
          {/* Desktop only: version chip → About dialog (null in browser). */}
          <span className="flex items-center gap-3">
            <VersionChip />
            <SettingsButton />
          </span>
        </div>
        <div className="flex items-center gap-2.5">
          {/* Desktop only: auto-update pill (null in browser / most phases). */}
          <UpdatePill />
          <Button variant="soft" onClick={pickImportFile} disabled={importMut.isPending}>
            {importMut.isPending ? <Spinner className="size-4" /> : <Upload size={15} />}
            Import
          </Button>
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            <Plus size={16} />
            New board
          </Button>
        </div>
      </header>

      {/* ---- Board grid / empty state ------------------------------- */}
      {boards.length === 0 ? (
        <section className="animate-fade-in bg-surface mx-auto mt-16 flex max-w-md flex-col items-center rounded-2xl border border-line-soft px-8 py-14 text-center">
          <div className="text-6xl" aria-hidden>
            🏆
          </div>
          <h2 className="font-display text-ink mt-5 text-xl font-bold">No boards yet</h2>
          <p className="text-ink-muted mt-2 text-sm leading-relaxed">
            Create your first board from scratch, or import an existing one — legacy{' '}
            <span className="text-ink font-semibold">.json</span> saves import directly.
          </p>
          <div className="mt-7 flex gap-2.5">
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              <Plus size={16} />
              New board
            </Button>
            <Button variant="soft" onClick={pickImportFile} disabled={importMut.isPending}>
              {importMut.isPending ? <Spinner className="size-4" /> : <Upload size={15} />}
              Import
            </Button>
          </div>
        </section>
      ) : (
        <section className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {boards.map((board) => (
            <BoardCard
              key={board.id}
              board={board}
              onOpen={openBoard}
              onPlay={playBoard}
              onMenu={openMenu}
            />
          ))}
        </section>
      )}

      {/* ---- Hidden import input ------------------------------------ */}
      <input
        ref={fileRef}
        type="file"
        accept=".jeopardy,.json,.zip"
        className="hidden"
        onChange={(e) => {
          const file = e.currentTarget.files?.[0]
          e.currentTarget.value = ''
          if (file) importMut.mutate(file)
        }}
      />

      {/* ---- Menus & dialogs ---------------------------------------- */}
      <ContextMenu state={menu} onClose={() => setMenu(null)} />

      <NameDialog
        open={createOpen}
        title="New board"
        initial="Untitled Board"
        submitLabel="Create"
        busy={createMut.isPending}
        onSubmit={(name) => createMut.mutate(name)}
        onClose={() => setCreateOpen(false)}
      />

      <NameDialog
        open={renaming !== null}
        title="Rename board"
        initial={renaming?.name ?? ''}
        submitLabel="Rename"
        busy={renameMut.isPending}
        onSubmit={(name) => {
          if (!renaming) return
          if (name === renaming.name) {
            setRenaming(null)
            return
          }
          renameMut.mutate({ id: renaming.id, name })
        }}
        onClose={() => setRenaming(null)}
      />

      <ConfirmDialog
        open={deleting !== null}
        title="Delete board"
        message={`Delete “${deleting?.name ?? ''}”? This permanently removes the board and all of its media.`}
        confirmLabel="Delete"
        danger
        onConfirm={() => {
          if (deleting) deleteMut.mutate(deleting)
        }}
        onCancel={() => setDeleting(null)}
      />
    </main>
  )
}
