/** About dialog for the desktop app: version, manual update check with live
 * status, current release notes (when the shell still has them), and the
 * version chip that opens it (rendered under the LibraryPage tagline).
 *
 * Desktop-only: both surfaces render null in a plain browser.
 */
import { useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Spinner } from '@/components/ui/Spinner'
import { desktop, isDesktop } from '@/lib/desktop'
import { notesForVersion } from '@/lib/releaseNotes'

import { ReleaseNotes } from './notes'
import { useUpdateState } from './useUpdateState'

/** Inline live status line under the "Check for updates" button. */
function UpdateStatusLine() {
  const state = useUpdateState()

  switch (state.phase) {
    case 'checking':
      return (
        <span className="text-ink-muted inline-flex items-center gap-1.5 text-sm">
          <Spinner className="size-3.5" />
          Checking…
        </span>
      )
    case 'up-to-date':
      return <span className="text-ink-muted text-sm">✓ You’re on the latest version</span>
    case 'downloading':
      return <span className="text-ink-muted text-sm">{Math.round(state.percent)}%</span>
    case 'ready':
      return (
        <Button variant="primary" size="sm" onClick={() => desktop?.updates.restartToUpdate()}>
          Restart
        </Button>
      )
    case 'error':
      return (
        <span className="inline-flex items-center gap-2 text-sm">
          <span className="text-danger">{state.message}</span>
          <Button variant="soft" size="sm" onClick={() => desktop?.updates.check()}>
            Retry
          </Button>
        </span>
      )
    default:
      return null
  }
}

export function AboutDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!desktop) return null

  // The app's own changelog section, baked in at build time — always
  // available, offline, on fresh installs and long after the post-update
  // What's-New was dismissed.
  const currentNotes = notesForVersion(desktop.appVersion)

  return (
    <Dialog open={open} onClose={onClose} title="About" className="w-full max-w-md">
      <div className="px-5 py-5">
        {/* ---- Identity ------------------------------------------- */}
        <div className="flex items-center gap-3">
          <span className="text-3xl" aria-hidden>
            🏆
          </span>
          <div>
            <div className="font-display text-ink text-lg font-bold tracking-wide">
              Chaewon Jeopardy
            </div>
            <div className="text-ink-muted text-sm">v{desktop.appVersion}</div>
          </div>
        </div>

        {/* ---- Updates -------------------------------------------- */}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button variant="soft" onClick={() => desktop?.updates.check()}>
            Check for updates
          </Button>
          <UpdateStatusLine />
        </div>

        {/* ---- What's new in the installed version ---------------- */}
        {currentNotes !== null && (
          <div className="border-line-soft mt-5 border-t pt-4">
            <h3 className="font-display text-ink mb-2 text-sm font-semibold">
              What’s new in v{desktop.appVersion}
            </h3>
            <ReleaseNotes notes={currentNotes} />
          </div>
        )}

        <p className="text-ink-faint mt-5 text-xs">
          Updates install automatically on restart.{' '}
          <a
            href="https://github.com/acohen1/jeopardy/releases"
            target="_blank"
            rel="noreferrer"
            className="text-accent hover:text-accent-bright underline-offset-2 hover:underline"
          >
            Full changelog
          </a>
        </p>
      </div>
    </Dialog>
  )
}

/** Small "v{appVersion}" chip that opens the About dialog. */
export function VersionChip() {
  const [open, setOpen] = useState(false)

  if (!isDesktop || !desktop) return null

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-ink-faint hover:text-ink mt-1.5 cursor-pointer text-xs tracking-wide transition-colors"
        title="About Chaewon Jeopardy"
      >
        v{desktop.appVersion}
      </button>
      <AboutDialog open={open} onClose={() => setOpen(false)} />
    </>
  )
}
