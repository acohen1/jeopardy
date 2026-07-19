/** SlideEditor — edits one slide DRAFT: text, ordered asset list (volume /
 * reorder / remove), add-media dropzone (click / drag-drop / paste), the
 * "Stack audio clips" toggle, and a live SlideView preview.
 *
 * Mirrors legacy slide_widgets.SlideEditor:
 *  - list order = collage position
 *  - stacking auto-enables when the 2nd audio is added; forced off below 2
 *  - max 4 collage cells (a stacked-audio group counts as one)
 */
import { ChevronDown, ChevronUp, LoaderCircle, Upload, X } from 'lucide-react'
import { useEffect, useImperativeHandle, useRef, useState } from 'react'
import type { Ref } from 'react'

import { uploadAsset } from '@/api/boards'
import { SlideView } from '@/components/slides/SlideView'
import { toast } from '@/components/ui/Toaster'
import { MEDIA_ACCEPT, defaultVolume, extToType, isRiskyVideo } from '@/lib/media'
import { MAX_SLIDE_CELLS, slideCellCount, slideIsFilled } from '@/types/board'
import type { Slide, SlideAsset } from '@/types/board'

export interface SlideEditorHandle {
  addFiles: (files: File[]) => void
  addPastedImage: (blob: Blob) => void
}

export interface SlideEditorProps {
  draft: Slide
  onChange: (next: Slide) => void
  boardId: string
  /** Lets the host dialog route clipboard pastes to the active tab. */
  handleRef?: Ref<SlideEditorHandle>
  /** False while this editor's tab is hidden — unmounts the live preview so
   * hidden media stops (display:none does not pause HTMLMediaElement). */
  active?: boolean
  /** Reports whether this editor has uploads in flight (host gates Save). */
  onUploadingChange?: (uploading: boolean) => void
}

const LIMIT_MSG = 'Maximum 4 items per slide (a stacked-audio group counts as one).'

const countAudio = (assets: SlideAsset[]) =>
  assets.filter((a) => a.asset_type === 'audio').length

export function SlideEditor({
  draft,
  onChange,
  boardId,
  handleRef,
  active = true,
  onUploadingChange,
}: SlideEditorProps) {
  const draftRef = useRef(draft)
  draftRef.current = draft
  const [uploading, setUploading] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const isUploading = uploading > 0
  useEffect(() => {
    onUploadingChange?.(isUploading)
  }, [isUploading, onUploadingChange])

  const commit = (next: Slide) => {
    draftRef.current = next
    onChange(next)
  }

  /** Commit an asset list; forces audio_stack off when <2 audio clips. */
  const commitAssets = (assets: SlideAsset[], stack?: boolean) => {
    const wanted = stack ?? draftRef.current.audio_stack
    commit({
      ...draftRef.current,
      assets,
      audio_stack: countAudio(assets) >= 2 ? wanted : false,
    })
  }

  const addOne = async (file: File | Blob, name: string) => {
    const type = extToType(name)
    if (!type) {
      toast(`Unsupported file type: ${name}`, { kind: 'error' })
      return
    }
    // Refuse before uploading (auto-stack means a 2nd+ audio still fits).
    {
      const d = draftRef.current
      const stack = d.audio_stack || (type === 'audio' && countAudio(d.assets) >= 1)
      const projected = [...d.assets, { path: '', asset_type: type, volume: 0 }]
      if (slideCellCount(projected, stack) > MAX_SLIDE_CELLS) {
        toast(LIMIT_MSG, { kind: 'error' })
        return
      }
    }
    if (type === 'video' && isRiskyVideo(name)) {
      toast('This container may not play in browsers — mp4/webm are safest.', { kind: 'info' })
    }

    setUploading((n) => n + 1)
    try {
      const res = await uploadAsset(boardId, file, file instanceof File ? undefined : name)
      const d = draftRef.current
      // Auto-enable stacking on the 2nd+ audio (legacy parity).
      const stack = d.audio_stack || (res.asset_type === 'audio' && countAudio(d.assets) >= 1)
      const next = [
        ...d.assets,
        { path: res.path, asset_type: res.asset_type, volume: defaultVolume(res.asset_type) },
      ]
      // Re-check with the server-confirmed type (drafts may have changed).
      if (slideCellCount(next, stack) > MAX_SLIDE_CELLS) {
        toast(LIMIT_MSG, { kind: 'error' })
        return
      }
      commitAssets(next, stack)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'unknown error'
      toast(`Upload failed — ${msg}`, { kind: 'error' })
    } finally {
      setUploading((n) => n - 1)
    }
  }

  const addFiles = (files: File[]) => {
    void (async () => {
      for (const f of files) await addOne(f, f.name)
    })()
  }

  const addPastedImage = (blob: Blob) => {
    void addOne(blob, 'pasted_image.png')
  }

  useImperativeHandle(handleRef, () => ({ addFiles, addPastedImage }))

  const move = (i: number, delta: number) => {
    const j = i + delta
    const assets = [...draftRef.current.assets]
    if (j < 0 || j >= assets.length) return
    ;[assets[i], assets[j]] = [assets[j], assets[i]]
    commitAssets(assets)
  }

  const remove = (i: number) => {
    commitAssets(draftRef.current.assets.filter((_, idx) => idx !== i))
  }

  const setVolume = (i: number, volume: number) => {
    commitAssets(
      draftRef.current.assets.map((a, idx) => (idx === i ? { ...a, volume } : a)),
    )
  }

  const audioCount = countAudio(draft.assets)

  return (
    <div
      className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto p-5"
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes('Files')) {
          e.preventDefault()
          setDragOver(true)
        }
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragOver(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        addFiles(Array.from(e.dataTransfer.files))
      }}
    >
      <div>
        <label className="text-accent-bright mb-1.5 block text-xs font-semibold tracking-wide">
          Text
        </label>
        <textarea
          value={draft.text}
          onChange={(e) => commit({ ...draftRef.current, text: e.target.value })}
          placeholder="Enter text for this slide…"
          rows={3}
          className="bg-surface text-ink placeholder:text-ink-faint focus:border-accent w-full resize-none rounded-lg border border-line p-2.5 text-sm transition-colors duration-100 focus:outline-none"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-accent-bright text-xs font-semibold tracking-wide">Assets</span>

        {draft.assets.map((a, i) => (
          <div
            key={`${a.path}-${i}`}
            className="bg-surface flex items-center gap-2 rounded-lg border border-line-soft px-2.5 py-1.5"
          >
            <span className="bg-cell text-ink-muted shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] font-bold tracking-wider">
              {a.asset_type.toUpperCase()}
            </span>
            <span className="text-ink min-w-0 flex-1 truncate text-sm" title={a.path}>
              {a.path}
            </span>

            {(a.asset_type === 'audio' || a.asset_type === 'video') && (
              <div className="flex w-36 shrink-0 items-center gap-1.5">
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={Math.round(a.volume * 100)}
                  onChange={(e) => setVolume(i, Number(e.target.value) / 100)}
                  aria-label={`Volume for ${a.path}`}
                />
                <span className="text-ink-muted w-9 shrink-0 text-right font-mono text-[11px] tabular-nums">
                  {Math.round(a.volume * 100)}%
                </span>
              </div>
            )}

            <div className="flex shrink-0 items-center gap-0.5">
              <RowButton label="Move earlier (up / left)" disabled={i === 0} onClick={() => move(i, -1)}>
                <ChevronUp size={14} />
              </RowButton>
              <RowButton
                label="Move later (down / right)"
                disabled={i === draft.assets.length - 1}
                onClick={() => move(i, 1)}
              >
                <ChevronDown size={14} />
              </RowButton>
              <RowButton label="Remove asset" danger onClick={() => remove(i)}>
                <X size={14} />
              </RowButton>
            </div>
          </div>
        ))}

        {uploading > 0 && (
          <div className="bg-surface text-ink-muted flex items-center gap-2 rounded-lg border border-line-soft px-2.5 py-1.5 text-sm">
            <LoaderCircle size={14} className="text-accent animate-spin" />
            Uploading…
          </div>
        )}

        {audioCount >= 2 && (
          <label className="text-ink-muted flex cursor-pointer items-center gap-2 px-0.5 text-sm">
            <input
              type="checkbox"
              checked={draft.audio_stack}
              onChange={(e) => commitAssets(draftRef.current.assets, e.target.checked)}
              className="accent-accent size-3.5 cursor-pointer"
            />
            Stack audio clips
            <span className="text-ink-faint text-xs">— overlay into one mixed track</span>
          </label>
        )}

        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className={
            dragOver
              ? 'bg-answer border-accent text-accent-bright flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-3 text-sm transition-colors duration-100'
              : 'text-ink-muted hover:border-accent/70 hover:text-ink flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-line px-4 py-3 text-sm transition-colors duration-100'
          }
        >
          <Upload size={15} />
          Add media — click, drop, or paste (Ctrl+V)
        </button>
        <input
          ref={fileInputRef}
          type="file"
          hidden
          multiple
          accept={MEDIA_ACCEPT}
          onChange={(e) => {
            addFiles(Array.from(e.target.files ?? []))
            e.target.value = ''
          }}
        />
      </div>

      <div className="flex min-h-44 flex-1 flex-col">
        <span className="text-accent-bright mb-1.5 text-xs font-semibold tracking-wide">
          Preview
        </span>
        <div className="bg-bg-deep flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-line-soft p-2">
          {active && slideIsFilled(draft) ? (
            <SlideView slide={draft} boardId={boardId} className="min-h-0 flex-1" />
          ) : (
            <div className="text-ink-faint flex flex-1 items-center justify-center text-sm">
              Preview appears here
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function RowButton({
  label,
  danger,
  disabled,
  onClick,
  children,
}: {
  label: string
  danger?: boolean
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={
        danger
          ? 'text-ink-muted hover:bg-cell hover:text-danger cursor-pointer rounded-md p-1 transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-35'
          : 'text-ink-muted hover:bg-cell hover:text-ink cursor-pointer rounded-md p-1 transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-35'
      }
    >
      {children}
    </button>
  )
}
