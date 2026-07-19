/** Board queries + mutations. Game-state mutations return the full updated
 * Board (server-authoritative) — we simply replace the cached copy. */
import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'

import { api } from './client'
import { toast } from '@/components/ui/Toaster'
import type { Board, BoardSummary } from '@/types/board'

export const boardsQuery = () =>
  queryOptions({
    queryKey: ['boards'],
    queryFn: () => api.get<BoardSummary[]>('/api/boards'),
  })

export const boardQuery = (boardId: string) =>
  queryOptions({
    queryKey: ['boards', boardId],
    queryFn: () => api.get<Board>(`/api/boards/${boardId}`),
  })

// ------------------------------------------------------------------ //
//  Library operations                                                //
// ------------------------------------------------------------------ //
export const createBoard = (name: string) => api.post<Board>('/api/boards', { name })
export const renameBoard = (id: string, name: string) => api.patch<Board>(`/api/boards/${id}`, { name })
export const deleteBoard = (id: string) => api.delete(`/api/boards/${id}`)
export const duplicateBoard = (id: string) => api.post<Board>(`/api/boards/${id}/duplicate`)
export const importBoard = (file: File) => api.upload<Board>('/api/boards/import', file)
export const exportBoardUrl = (id: string) => `/api/boards/${id}/export`

/** Full-document save used by the editor (debounced autosave). */
export const saveBoard = (board: Board) => api.put<Board>(`/api/boards/${board.id}`, board)

// ------------------------------------------------------------------ //
//  Asset upload                                                      //
// ------------------------------------------------------------------ //
export interface AssetUploadResult {
  path: string
  asset_type: 'image' | 'gif' | 'video' | 'audio'
}

export const uploadAsset = (boardId: string, file: File | Blob, filename?: string) =>
  api.upload<AssetUploadResult>(`/api/boards/${boardId}/assets`, file, filename)

// ------------------------------------------------------------------ //
//  Game-state mutations (play mode)                                  //
// ------------------------------------------------------------------ //
/**
 * Play-mode mutations. Each takes its arguments as a single tuple — callers
 * write `award.mutate(['Alex', 400])`.
 *
 * Every fire is stamped with a monotonically increasing sequence number
 * (onMutate); a response may write the cache only if its stamp is newer than
 * the last one applied, so a slow out-of-order response can never revert a
 * newer board. On error we toast the message and invalidate the board query
 * so the UI resyncs to server truth.
 */
export function useGameActions(boardId: string) {
  const qc = useQueryClient()
  const queryKey = boardQuery(boardId).queryKey
  const base = `/api/boards/${boardId}`

  const seqRef = useRef({ fired: 0, applied: 0 })
  const onMutate = () => ({ seq: ++seqRef.current.fired })
  const onSuccess = (board: Board, _vars: unknown, res: { seq: number }) => {
    if (res.seq <= seqRef.current.applied) return
    seqRef.current.applied = res.seq
    qc.setQueryData(queryKey, board)
  }
  const onError = (error: Error) => {
    toast(error.message, { kind: 'error' })
    void qc.invalidateQueries({ queryKey })
  }

  const addPlayer = useMutation({
    mutationFn: ([name]: [name: string]) => api.post<Board>(`${base}/players`, { name }),
    onMutate,
    onSuccess,
    onError,
  })

  const removePlayer = useMutation({
    mutationFn: ([name]: [name: string]) =>
      api.delete<Board>(`${base}/players/${encodeURIComponent(name)}`),
    onMutate,
    onSuccess,
    onError,
  })

  const renamePlayer = useMutation({
    mutationFn: ([oldName, newName]: [oldName: string, newName: string]) =>
      api.patch<Board>(`${base}/players/${encodeURIComponent(oldName)}`, { name: newName }),
    onMutate,
    onSuccess,
    onError,
  })

  const award = useMutation({
    mutationFn: ([name, delta, note]: [name: string, delta: number, note?: string]) =>
      api.post<Board>(`${base}/players/${encodeURIComponent(name)}/award`, {
        delta,
        note: note ?? '',
      }),
    onMutate,
    onSuccess,
    onError,
  })

  /** Host correction: set an absolute score (logged to history). */
  const setScore = useMutation({
    mutationFn: ([name, score, note]: [name: string, score: number, note?: string]) =>
      api.put<Board>(`${base}/players/${encodeURIComponent(name)}/score`, {
        score,
        note: note ?? '',
      }),
    onMutate,
    onSuccess,
    onError,
  })

  /** Reverse the most recent scoring action (award, deduct, or manual set). */
  const undoScore = useMutation({
    mutationFn: (_: []) => api.post<Board>(`${base}/history/undo`),
    onMutate,
    onSuccess,
    onError,
  })

  const resetScores = useMutation({
    mutationFn: (_: []) => api.post<Board>(`${base}/scores/reset`),
    onMutate,
    onSuccess,
    onError,
  })

  const setCellUsed = useMutation({
    mutationFn: ([row, col, used]: [row: number, col: number, used: boolean]) =>
      api.put<Board>(`${base}/cells/${row}/${col}/used`, { used }),
    onMutate,
    onSuccess,
    onError,
  })

  const resetUsed = useMutation({
    mutationFn: (_: []) => api.post<Board>(`${base}/cells/reset-used`),
    onMutate,
    onSuccess,
    onError,
  })

  const setAllowNegatives = useMutation({
    mutationFn: ([allow]: [allow: boolean]) =>
      api.put<Board>(`${base}/settings`, { allow_negatives: allow }),
    onMutate,
    onSuccess,
    onError,
  })

  return {
    addPlayer,
    removePlayer,
    renamePlayer,
    award,
    setScore,
    undoScore,
    resetScores,
    setCellUsed,
    resetUsed,
    setAllowNegatives,
  }
}
