/** App-wide toasts. Emitted from anywhere via toast(); rendered bottom-center
 * (legacy overlay-toast placement). */
import { clsx } from 'clsx'
import { useEffect, useState } from 'react'

export type ToastKind = 'success' | 'error' | 'info'

interface ToastItem {
  id: number
  text: string
  kind: ToastKind
  leaving: boolean
}

interface ToastOptions {
  kind?: ToastKind
  /** Visible time in ms before fade-out (legacy: 1500). */
  duration?: number
}

type Listener = (text: string, opts: ToastOptions) => void
let listener: Listener | null = null

export function toast(text: string, opts: ToastOptions = {}) {
  listener?.(text, opts)
}

const KIND_STYLES: Record<ToastKind, string> = {
  success: 'bg-[#1a5a1a] text-[#aaffaa] border-[#2a7a2a]',
  error: 'bg-[#5a1a1a] text-[#ffaaaa] border-[#7a2a2a]',
  info: 'bg-surface text-ink border-line',
}

let nextId = 1

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([])

  useEffect(() => {
    listener = (text, opts) => {
      const id = nextId++
      const duration = opts.duration ?? 1500
      setItems((prev) => [...prev, { id, text, kind: opts.kind ?? 'info', leaving: false }])
      window.setTimeout(() => {
        setItems((prev) => prev.map((t) => (t.id === id ? { ...t, leaving: true } : t)))
      }, duration)
      window.setTimeout(() => {
        setItems((prev) => prev.filter((t) => t.id !== id))
      }, duration + 400)
    }
    return () => {
      listener = null
    }
  }, [])

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-32 z-[70] flex flex-col items-center gap-2">
      {items.map((t) => (
        <div
          key={t.id}
          className={clsx(
            'animate-toast-in rounded-lg border px-5 py-2 text-sm font-bold shadow-raised transition-opacity duration-400',
            KIND_STYLES[t.kind],
            t.leaving && 'opacity-0',
          )}
        >
          {t.text}
        </div>
      ))}
    </div>
  )
}
