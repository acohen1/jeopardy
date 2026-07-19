/** Window-level hotkeys. Keys are KeyboardEvent.key values ('a', ' ',
 * 'ArrowLeft', 'Escape', …). Handlers are skipped while typing in form
 * fields unless allowInInputs is set. */
import { useEffect, useRef } from 'react'

import { anyModalOpen } from '@/lib/modalState'

export interface UseHotkeysOptions {
  enabled?: boolean
  allowInInputs?: boolean
  /** Keep firing even while a modal Dialog is open (rarely wanted). */
  allowInModals?: boolean
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

export function useHotkeys(
  map: Record<string, (e: KeyboardEvent) => void>,
  { enabled = true, allowInInputs = false, allowInModals = false }: UseHotkeysOptions = {},
) {
  // Keep the latest map without re-binding the listener each render
  const mapRef = useRef(map)
  mapRef.current = map

  useEffect(() => {
    if (!enabled) return
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (!allowInModals && anyModalOpen()) return
      if (!allowInInputs && isTypingTarget(e.target)) return
      const handler = mapRef.current[e.key] ?? mapRef.current[e.key.toLowerCase()]
      if (handler) {
        e.preventDefault()
        handler(e)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [enabled, allowInInputs])
}
