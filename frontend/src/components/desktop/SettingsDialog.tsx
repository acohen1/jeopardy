/** Settings dialog (desktop only): where boards are stored, and LAN/TV access.
 * Opened from the gear button next to the version chip on the library page. */
import { FolderOpen, FolderSync, Settings, Tv } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/components/ui/Toaster'
import { desktop, isDesktop } from '@/lib/desktop'

/** Data-directory section: where boards live, open it, relocate it. */
function StorageSection({ open }: { open: boolean }) {
  const [info, setInfo] = useState<{ path: string; boardCount: number; isDefault: boolean } | null>(
    null,
  )
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(() => {
    desktop?.storage
      .getInfo()
      .then(setInfo)
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (open) refresh()
  }, [open, refresh])

  if (!info) return null

  const relocate = async () => {
    setBusy(true)
    try {
      const result = await desktop?.storage.choose()
      if (result) {
        toast('Data folder updated', { kind: 'success' })
        refresh()
      }
    } catch {
      toast('Could not change the data folder', { kind: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const reset = async () => {
    setBusy(true)
    try {
      await desktop?.storage.resetToDefault()
      toast('Back to the default data folder', { kind: 'success' })
      refresh()
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h3 className="font-display text-ink mb-1.5 text-sm font-semibold">Storage</h3>
      <p className="text-ink-muted text-xs leading-relaxed">
        Your boards live in
        <br />
        <span className="text-ink font-mono text-[11px] break-all">{info.path}</span>
        <br />
        <span className="text-ink-faint">
          {info.boardCount} board{info.boardCount === 1 ? '' : 's'}
          {info.isDefault ? ' · default location' : ' · custom location'}
        </span>
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => desktop?.storage.openFolder()}>
          <FolderOpen size={13} />
          Open folder
        </Button>
        <Button variant="soft" size="sm" disabled={busy} onClick={relocate}>
          {busy ? <Spinner className="size-3.5" /> : <FolderSync size={13} />}
          Change…
        </Button>
        {!info.isDefault && (
          <Button variant="ghost" size="sm" disabled={busy} onClick={reset}>
            Reset to default
          </Button>
        )}
      </div>
    </section>
  )
}

/** LAN / TV-view access: expose the app to devices on the same wifi. */
function LanSection({ open }: { open: boolean }) {
  const [info, setInfo] = useState<{ enabled: boolean; urls: string[] } | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(() => {
    desktop?.lan
      .get()
      .then(setInfo)
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (open) refresh()
  }, [open, refresh])

  if (!info) return null

  const toggle = async () => {
    setBusy(true)
    try {
      await desktop?.lan.set(!info.enabled)
      toast(info.enabled ? 'Wifi access off' : 'Wifi access on', { kind: 'success' })
      refresh()
    } catch {
      toast('Could not change wifi access', { kind: 'error' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="border-line-soft mt-5 border-t pt-4">
      <h3 className="font-display text-ink mb-1.5 flex items-center gap-1.5 text-sm font-semibold">
        <Tv size={14} className="text-accent" aria-hidden />
        TV &amp; wifi access
      </h3>
      <p className="text-ink-muted text-xs leading-relaxed">
        Let a TV, tablet, or phone on the same wifi open the game in its browser — great for a
        second screen while you host from the laptop.
      </p>
      <div className="mt-3 flex items-center gap-3">
        <Button variant={info.enabled ? 'danger' : 'primary'} size="sm" disabled={busy} onClick={toggle}>
          {busy ? <Spinner className="size-3.5" /> : info.enabled ? 'Turn off' : 'Turn on'}
        </Button>
        {info.enabled && info.urls.length > 0 && (
          <span className="text-xs">
            <span className="text-ink-faint">On the TV, open </span>
            <span className="text-accent-bright font-mono text-[11px]">{info.urls[0]}</span>
          </span>
        )}
      </div>
      {info.enabled && (
        <p className="text-ink-faint mt-2 text-[11px]">
          Windows may ask to allow network access the first time — choose Allow.
        </p>
      )}
    </section>
  )
}

export function SettingsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!desktop) return null
  return (
    <Dialog open={open} onClose={onClose} title="Settings" className="w-full max-w-md">
      <div className="px-5 py-5">
        <StorageSection open={open} />
        <LanSection open={open} />
      </div>
    </Dialog>
  )
}

/** Small gear button that opens Settings (rendered beside the version chip). */
export function SettingsButton() {
  const [open, setOpen] = useState(false)

  if (!isDesktop) return null

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-ink-faint hover:text-ink mt-1.5 inline-flex cursor-pointer items-center gap-1 text-xs tracking-wide transition-colors"
        title="Settings"
      >
        <Settings size={12} aria-hidden />
        Settings
      </button>
      <SettingsDialog open={open} onClose={() => setOpen(false)} />
    </>
  )
}
