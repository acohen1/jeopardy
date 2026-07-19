/** Header pill in the library page surfacing the auto-updater.
 *
 * ready → accent pill "v{version} ready · Restart" (click = restart & install)
 * downloading → subtle ghost pill "Updating… {percent}%"
 * anything else (or not desktop) → renders nothing.
 *
 * Also fires a one-time info toast the first time a given version reaches
 * 'ready', so the user hears about it even if they never look up here.
 */
import { Sparkles } from 'lucide-react'
import { useEffect } from 'react'

import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toaster'
import { desktop, isDesktop } from '@/lib/desktop'

import { useUpdateState } from './useUpdateState'

/** Versions we've already announced via toast (module-level: once per session). */
const announcedVersions = new Set<string>()

export function UpdatePill() {
  const state = useUpdateState()

  useEffect(() => {
    if (state.phase !== 'ready') return
    if (announcedVersions.has(state.version)) return
    announcedVersions.add(state.version)
    toast(`Update v${state.version} downloaded — restart when convenient`, {
      kind: 'info',
      duration: 5000,
    })
  }, [state])

  if (!isDesktop) return null

  if (state.phase === 'ready') {
    return (
      <Button
        variant="primary"
        size="sm"
        className="rounded-full"
        onClick={() => desktop?.updates.restartToUpdate()}
        title="Quit and install the downloaded update"
      >
        <Sparkles size={13} />
        v{state.version} ready · Restart
      </Button>
    )
  }

  if (state.phase === 'downloading') {
    return (
      <span className="text-ink-muted border-line/60 inline-flex items-center gap-1.5 rounded-full border bg-transparent px-2.5 py-1 text-xs">
        <Spinner className="size-3.5" />
        Updating… {Math.round(state.percent)}%
      </span>
    )
  }

  return null
}
