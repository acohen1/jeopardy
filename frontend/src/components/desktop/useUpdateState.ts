/** Live auto-update state from the Electron bridge.
 *
 * Subscribes to desktop.updates.onState and seeds from getState(). In a plain
 * browser (no bridge) it stays at {phase:'idle'} forever.
 */
import { useEffect, useState } from 'react'

import { desktop, type UpdateState } from '@/lib/desktop'

const IDLE: UpdateState = { phase: 'idle' }

export function useUpdateState(): UpdateState {
  const [state, setState] = useState<UpdateState>(IDLE)

  useEffect(() => {
    if (!desktop) return

    let alive = true
    let sawEvent = false

    const unsubscribe = desktop.updates.onState((next) => {
      sawEvent = true
      if (alive) setState(next)
    })

    // Seed with the current state, but never clobber a fresher event that
    // arrived while getState() was in flight.
    desktop.updates
      .getState()
      .then((seed) => {
        if (alive && !sawEvent) setState(seed)
      })
      .catch(() => {
        /* bridge unavailable mid-teardown — keep whatever we have */
      })

    return () => {
      alive = false
      unsubscribe()
    }
  }, [])

  return state
}
