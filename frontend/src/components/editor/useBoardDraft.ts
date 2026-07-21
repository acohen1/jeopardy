/** Local working copy of a Board + debounced (~800ms) full-document autosave.
 * The editor owns the whole doc; every successful PUT re-syncs the
 * ['boards', id] query cache so other routes read the saved copy. */
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { boardQuery, saveBoard } from '@/api/boards'
import { toast } from '@/components/ui/Toaster'
import type { Board } from '@/types/board'

export type SaveStatus = 'saved' | 'saving' | 'error'

export interface BoardDraft {
  board: Board
  status: SaveStatus
  /** Apply a local edit; schedules the debounced autosave. */
  update: (updater: (b: Board) => Board) => void
  /** Cancel the debounce and save now. Resolves true once the doc is clean. */
  flush: () => Promise<boolean>
  /** Restore the previous snapshot (dirty + autosave, same as update). */
  undo: () => void
  /** Re-apply the last undone snapshot. */
  redo: () => void
  canUndo: boolean
  canRedo: boolean
}

const AUTOSAVE_MS = 800
const HISTORY_CAP = 50

export function useBoardDraft(initial: Board): BoardDraft {
  const qc = useQueryClient()
  const [board, setBoard] = useState(initial)
  const [status, setStatus] = useState<SaveStatus>('saved')

  const boardRef = useRef(board)
  const dirtyRef = useRef(false)
  const timerRef = useRef<number | undefined>(undefined)
  const inFlightRef = useRef<Promise<boolean> | null>(null)

  // Undo/redo stacks of full Board snapshots. Kept in refs (no extra renders);
  // every push/pop happens alongside a setBoard call, so the canUndo/canRedo
  // booleans computed at render time are always fresh.
  const undoStackRef = useRef<Board[]>([])
  const redoStackRef = useRef<Board[]>([])

  const runSave = useCallback(async (): Promise<boolean> => {
    dirtyRef.current = false
    setStatus('saving')
    try {
      const saved = await saveBoard(boardRef.current)
      qc.setQueryData(boardQuery(saved.id).queryKey, saved)
      // Edits arrived while the PUT was in flight — save again.
      if (dirtyRef.current) return runSave()
      setStatus('saved')
      return true
    } catch {
      dirtyRef.current = true
      setStatus('error')
      toast('Autosave failed — will retry on the next change', { kind: 'error' })
      return false
    }
  }, [qc])

  const flush = useCallback((): Promise<boolean> => {
    window.clearTimeout(timerRef.current)
    if (inFlightRef.current) return inFlightRef.current
    if (!dirtyRef.current) return Promise.resolve(true)
    const p = runSave().finally(() => {
      inFlightRef.current = null
    })
    inFlightRef.current = p
    return p
  }, [runSave])

  /** Make `next` the live draft: dirty + (re)scheduled autosave. Shared by
   * update/undo/redo so a restored snapshot persists exactly like an edit. */
  const apply = useCallback(
    (next: Board) => {
      boardRef.current = next
      setBoard(next)
      dirtyRef.current = true
      setStatus('saving')
      window.clearTimeout(timerRef.current)
      timerRef.current = window.setTimeout(() => void flush(), AUTOSAVE_MS)
    },
    [flush],
  )

  const update = useCallback(
    (updater: (b: Board) => Board) => {
      const prev = boardRef.current
      const next = updater(prev)
      undoStackRef.current.push(prev)
      if (undoStackRef.current.length > HISTORY_CAP) undoStackRef.current.shift()
      redoStackRef.current = [] // a fresh edit invalidates the redo branch
      apply(next)
    },
    [apply],
  )

  const undo = useCallback(() => {
    const prev = undoStackRef.current.pop()
    if (!prev) return
    redoStackRef.current.push(boardRef.current)
    apply(prev)
  }, [apply])

  const redo = useCallback(() => {
    const next = redoStackRef.current.pop()
    if (!next) return
    undoStackRef.current.push(boardRef.current)
    apply(next)
  }, [apply])

  // Native 'unsaved changes' prompt on tab close/refresh while the draft is
  // dirty (debounce pending or last save failed) or a save is in flight.
  // Checked at event time via refs, so no re-subscription per state change.
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirtyRef.current && !inFlightRef.current) return
      e.preventDefault()
      // Legacy Chrome requires returnValue to be set for the prompt to show.
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [])

  // Last-chance save when the editor unmounts (navigating away mid-debounce).
  useEffect(
    () => () => {
      window.clearTimeout(timerRef.current)
      if (dirtyRef.current && !inFlightRef.current) {
        dirtyRef.current = false
        saveBoard(boardRef.current)
          .then((saved) => qc.setQueryData(boardQuery(saved.id).queryKey, saved))
          .catch(() => undefined)
      }
    },
    [qc],
  )

  return {
    board,
    status,
    update,
    flush,
    undo,
    redo,
    canUndo: undoStackRef.current.length > 0,
    canRedo: redoStackRef.current.length > 0,
  }
}
