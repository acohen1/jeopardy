import { useEffect } from 'react'

/** Keep the phone's screen on while the controller is up.
 * Wake locks are auto-released when the tab is hidden, so we re-request on
 * visibilitychange. Unsupported browsers / denials fail silently — the
 * feature is a nicety, never a requirement. */
export function useWakeLock(): void {
  useEffect(() => {
    let sentinel: WakeLockSentinel | null = null
    let disposed = false

    const request = async () => {
      try {
        const s = await navigator.wakeLock?.request('screen')
        if (disposed) {
          await s?.release()
        } else {
          sentinel = s ?? null
        }
      } catch {
        // Silent — low battery, unsupported, or backgrounded tab.
      }
    }

    void request()
    const onVisibility = () => {
      if (document.visibilityState === 'visible') void request()
    }
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      disposed = true
      document.removeEventListener('visibilitychange', onVisibility)
      sentinel?.release().catch(() => undefined)
    }
  }, [])
}
