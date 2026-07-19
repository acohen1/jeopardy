import { clsx } from 'clsx'
import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

import { registerModal, unregisterModal } from '@/lib/modalState'

export interface DialogProps {
  open: boolean
  onClose: () => void
  title?: string
  /** Extra content rendered to the right of the title (e.g. tabs). */
  titleExtra?: React.ReactNode
  children: React.ReactNode
  className?: string
  /** Close when the backdrop is clicked (default true). */
  dismissable?: boolean
}

export function Dialog({
  open,
  onClose,
  title,
  titleExtra,
  children,
  className,
  dismissable = true,
}: DialogProps) {
  // Register as an open modal so page-level hotkeys (useHotkeys) suspend —
  // Escape/Space/etc. must drive the dialog, not the page behind it.
  useEffect(() => {
    if (!open) return
    registerModal()
    return unregisterModal
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        // A video fullscreened from inside the dialog: let Esc exit
        // fullscreen (the browser handles that) instead of closing us.
        if (document.fullscreenElement) return
        e.preventDefault()
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6 backdrop-blur-[2px]"
      onMouseDown={(e) => {
        if (dismissable && e.target === e.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={clsx(
          'animate-scale-in bg-bg shadow-overlay flex max-h-full flex-col overflow-hidden rounded-2xl border border-line/70',
          className,
        )}
      >
        {(title !== undefined || titleExtra !== undefined) && (
          <div className="flex items-center gap-3 border-b border-line-soft px-5 py-3.5">
            {title !== undefined && (
              <h2 className="font-display text-ink text-base font-semibold">{title}</h2>
            )}
            {titleExtra}
            <button
              type="button"
              onClick={onClose}
              className="text-ink-muted hover:bg-surface hover:text-ink ml-auto cursor-pointer rounded-md p-1 transition-colors"
              aria-label="Close"
            >
              <X size={17} />
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
