/** Editor toolbar — back link, inline board name, size steppers, autosave
 * status chip, and the Play launcher. */
import { Link } from '@tanstack/react-router'
import {
  ArrowLeft,
  Check,
  LoaderCircle,
  Minus,
  Play,
  Plus,
  Redo2,
  TriangleAlert,
  Undo2,
} from 'lucide-react'

import { Button } from '@/components/ui/Button'
import type { SaveStatus } from '@/components/editor/useBoardDraft'

export interface EditorToolbarProps {
  name: string
  numRows: number
  numCols: number
  status: SaveStatus
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  onRename: (name: string) => void
  onResize: (rows: number, cols: number) => void
  onPlay: () => void
}

export function EditorToolbar({
  name,
  numRows,
  numCols,
  status,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onRename,
  onResize,
  onPlay,
}: EditorToolbarProps) {
  return (
    <header className="bg-bg-deep/50 flex flex-wrap items-center gap-3 border-b border-line-soft px-4 py-2.5">
      <Link
        to="/"
        className="text-ink-muted hover:bg-surface hover:text-ink flex items-center gap-1.5 rounded-lg border border-line/60 px-2.5 py-1.5 text-sm transition-colors duration-100 hover:border-line"
      >
        <ArrowLeft size={15} />
        Library
      </Link>

      <input
        value={name}
        onChange={(e) => onRename(e.target.value)}
        placeholder="Untitled board"
        aria-label="Board name"
        className="font-display text-ink placeholder:text-ink-faint focus:border-accent focus:bg-surface/50 w-64 rounded-lg border border-transparent bg-transparent px-2.5 py-1 text-lg font-semibold transition-colors duration-100 hover:border-line-soft focus:outline-none"
      />

      <div className="mx-1 h-6 w-px bg-line-soft" aria-hidden />

      <Stepper label="Rows" value={numRows} min={1} max={10} onChange={(v) => onResize(v, numCols)} />
      <Stepper label="Cols" value={numCols} min={1} max={12} onChange={(v) => onResize(numRows, v)} />

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          disabled={!canUndo}
          onClick={onUndo}
          title="Undo (Ctrl+Z)"
          aria-label="Undo"
          className="px-1.5 py-1.5"
        >
          <Undo2 size={14} />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={!canRedo}
          onClick={onRedo}
          title="Redo (Ctrl+Y)"
          aria-label="Redo"
          className="px-1.5 py-1.5"
        >
          <Redo2 size={14} />
        </Button>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <StatusChip status={status} />
        <Button variant="primary" onClick={onPlay} className="px-5">
          <Play size={14} fill="currentColor" />
          Play
        </Button>
      </div>
    </header>
  )
}

function Stepper({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  onChange: (value: number) => void
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-ink-muted text-xs font-semibold">{label}</span>
      <div className="bg-surface flex items-center rounded-lg border border-line/70">
        <button
          type="button"
          aria-label={`Fewer ${label.toLowerCase()}`}
          disabled={value <= min}
          onClick={() => onChange(Math.max(min, value - 1))}
          className="text-ink-muted hover:bg-cell hover:text-ink cursor-pointer rounded-l-lg p-1.5 transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-35"
        >
          <Minus size={13} />
        </button>
        <span className="text-ink w-6 text-center font-mono text-sm tabular-nums">{value}</span>
        <button
          type="button"
          aria-label={`More ${label.toLowerCase()}`}
          disabled={value >= max}
          onClick={() => onChange(Math.min(max, value + 1))}
          className="text-ink-muted hover:bg-cell hover:text-ink cursor-pointer rounded-r-lg p-1.5 transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-35"
        >
          <Plus size={13} />
        </button>
      </div>
    </div>
  )
}

function StatusChip({ status }: { status: SaveStatus }) {
  if (status === 'saving') {
    return (
      <span className="text-ink-muted flex items-center gap-1.5 rounded-full border border-line/60 px-2.5 py-1 text-xs">
        <LoaderCircle size={12} className="animate-spin" />
        Saving…
      </span>
    )
  }
  if (status === 'error') {
    return (
      <span className="text-danger border-danger-deep flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs">
        <TriangleAlert size={12} />
        Save failed
      </span>
    )
  }
  return (
    <span className="text-accent border-accent/30 flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs">
      <Check size={12} />
      Saved
    </span>
  )
}
