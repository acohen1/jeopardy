/** CellEditorDialog — Question/Answer tabbed editor over DRAFT copies of a
 * cell's slides. Save commits both drafts; Cancel/Escape discards (legacy
 * OK/Cancel parity). Pastes anywhere in the dialog land in the active tab. */
import { clsx } from 'clsx'
import { LoaderCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { SlideEditor } from '@/components/editor/SlideEditor'
import type { SlideEditorHandle } from '@/components/editor/SlideEditor'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Dialog } from '@/components/ui/Dialog'
import type { Cell, Slide } from '@/types/board'

export interface CellEditorDialogProps {
  cell: Cell
  boardId: string
  title: string
  onSave: (question: Slide, answer: Slide) => void
  onCancel: () => void
}

type Tab = 'question' | 'answer'
const TABS: Tab[] = ['question', 'answer']

const cloneSlide = (s: Slide): Slide => ({
  text: s.text,
  audio_stack: s.audio_stack,
  assets: s.assets.map((a) => ({ ...a })),
})

/** Trim text + drop a dangling audio_stack flag (legacy get_slide parity). */
const finalizeSlide = (s: Slide): Slide => ({
  ...s,
  text: s.text.trim(),
  audio_stack:
    s.assets.filter((a) => a.asset_type === 'audio').length >= 2 ? s.audio_stack : false,
})

export function CellEditorDialog({ cell, boardId, title, onSave, onCancel }: CellEditorDialogProps) {
  const [tab, setTab] = useState<Tab>('question')
  const [qDraft, setQDraft] = useState<Slide>(() => cloneSlide(cell.question_slide))
  const [aDraft, setADraft] = useState<Slide>(() => cloneSlide(cell.answer_slide))
  const [qUploading, setQUploading] = useState(false)
  const [aUploading, setAUploading] = useState(false)
  const uploading = qUploading || aUploading

  const qRef = useRef<SlideEditorHandle | null>(null)
  const aRef = useRef<SlideEditorHandle | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)

  // Guard against silently losing typed work: Cancel/Escape on a dirty
  // draft asks before discarding (the drafts live only in this dialog).
  const initialRef = useRef(JSON.stringify([qDraft, aDraft]))
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const requestCancel = () => {
    if (JSON.stringify([qDraft, aDraft]) !== initialRef.current) setConfirmDiscard(true)
    else onCancel()
  }

  // Focus the dialog body so clipboard pastes are caught even before the user
  // clicks into a field.
  useEffect(() => {
    bodyRef.current?.focus()
  }, [])

  const handlePaste = (e: React.ClipboardEvent) => {
    const target = tab === 'question' ? qRef.current : aRef.current
    if (!target) return
    const files = Array.from(e.clipboardData.files)
    if (files.length > 0) {
      e.preventDefault()
      target.addFiles(files)
      return
    }
    // Raw image data (e.g. a copied screenshot region) → pasted_image.png
    const item = Array.from(e.clipboardData.items).find((i) => i.type.startsWith('image/'))
    const blob = item?.getAsFile()
    if (blob) {
      e.preventDefault()
      target.addPastedImage(blob)
    }
  }

  return (
    <Dialog
      open
      onClose={requestCancel}
      title={title}
      dismissable={false}
      className="h-[86vh] w-full max-w-3xl"
      titleExtra={
        <div className="bg-surface ml-2 flex rounded-lg border border-line/60 p-0.5">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={clsx(
                'cursor-pointer rounded-md px-3.5 py-1 text-xs font-semibold capitalize transition-colors duration-100',
                tab === t
                  ? 'bg-surface-warm text-accent-bright'
                  : 'text-ink-muted hover:text-ink',
              )}
            >
              {t}
            </button>
          ))}
        </div>
      }
    >
      <div
        ref={bodyRef}
        tabIndex={-1}
        onPaste={handlePaste}
        className="flex h-full min-h-0 flex-col outline-none"
      >
        <div className={clsx('min-h-0 flex-1', tab !== 'question' && 'hidden')}>
          <SlideEditor
            draft={qDraft}
            onChange={setQDraft}
            boardId={boardId}
            handleRef={qRef}
            active={tab === 'question'}
            onUploadingChange={setQUploading}
          />
        </div>
        <div className={clsx('min-h-0 flex-1', tab !== 'answer' && 'hidden')}>
          <SlideEditor
            draft={aDraft}
            onChange={setADraft}
            boardId={boardId}
            handleRef={aRef}
            active={tab === 'answer'}
            onUploadingChange={setAUploading}
          />
        </div>

        <div className="flex shrink-0 items-center justify-end gap-2 border-t border-line-soft px-5 py-3">
          {uploading && (
            <span className="text-ink-muted flex items-center gap-1.5 text-xs">
              <LoaderCircle size={13} className="text-accent animate-spin" />
              Uploading…
            </span>
          )}
          <Button variant="ghost" onClick={requestCancel}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={uploading}
            onClick={() => onSave(finalizeSlide(qDraft), finalizeSlide(aDraft))}
          >
            Save
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDiscard}
        title="Discard changes?"
        message="This cell has unsaved edits. Discard them?"
        confirmLabel="Discard"
        danger
        onConfirm={() => {
          setConfirmDiscard(false)
          onCancel()
        }}
        onCancel={() => setConfirmDiscard(false)}
      />
    </Dialog>
  )
}
