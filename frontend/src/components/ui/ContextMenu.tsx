/** Right-click context menu (portal at cursor, viewport-clamped). */
import { clsx } from 'clsx'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export type ContextMenuItem =
  | { type?: 'item'; label: string; onSelect: () => void; danger?: boolean; disabled?: boolean }
  | { type: 'heading'; label: string }
  | { type: 'separator' }

export interface ContextMenuState {
  x: number
  y: number
  items: ContextMenuItem[]
}

export interface ContextMenuProps {
  state: ContextMenuState | null
  onClose: () => void
}

export function ContextMenu({ state, onClose }: ContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)

  useLayoutEffect(() => {
    if (!state || !ref.current) {
      setPos(null)
      return
    }
    const rect = ref.current.getBoundingClientRect()
    setPos({
      x: Math.min(state.x, window.innerWidth - rect.width - 8),
      y: Math.min(state.y, window.innerHeight - rect.height - 8),
    })
  }, [state])

  useEffect(() => {
    if (!state) return
    const close = () => onClose()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    // Defer so the opening right-click itself doesn't immediately close it
    const t = window.setTimeout(() => {
      window.addEventListener('pointerdown', close)
      window.addEventListener('scroll', close, true)
      window.addEventListener('keydown', onKey)
    })
    return () => {
      window.clearTimeout(t)
      window.removeEventListener('pointerdown', close)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('keydown', onKey)
    }
  }, [state, onClose])

  if (!state) return null

  return createPortal(
    <div
      ref={ref}
      className="bg-surface shadow-overlay fixed z-[60] min-w-44 rounded-lg border border-line p-1"
      style={{
        left: pos?.x ?? state.x,
        top: pos?.y ?? state.y,
        visibility: pos ? 'visible' : 'hidden',
      }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {state.items.map((item, i) => {
        if (item.type === 'separator') {
          return <div key={i} className="mx-2 my-1 h-px bg-line" />
        }
        if (item.type === 'heading') {
          return (
            <div
              key={i}
              className="text-ink-faint px-3 pt-1.5 pb-0.5 text-[11px] font-semibold tracking-wide uppercase"
            >
              {item.label}
            </div>
          )
        }
        return (
          <button
            key={i}
            type="button"
            disabled={item.disabled}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => {
              item.onSelect()
              onClose()
            }}
            className={clsx(
              'block w-full cursor-pointer rounded-md px-3 py-1.5 text-left text-sm transition-colors',
              item.danger
                ? 'text-danger hover:bg-[#3a2828]'
                : 'text-ink hover:bg-accent-deep hover:text-ink',
              item.disabled && 'cursor-not-allowed opacity-40 hover:bg-transparent',
            )}
          >
            {item.label}
          </button>
        )
      })}
    </div>,
    document.body,
  )
}
