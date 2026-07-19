/** Post-update "What's new" dialog, mounted once in the root layout.
 *
 * On mount (desktop only) asks the shell for pending release notes — non-null
 * exactly once after an update — and shows them until the user dismisses.
 */
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { desktop, type WhatsNew } from '@/lib/desktop'

import { ReleaseNotes } from './notes'

export function WhatsNewDialog() {
  const [whatsNew, setWhatsNew] = useState<WhatsNew | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!desktop) return
    let alive = true
    desktop.whatsNew
      .get()
      .then((wn) => {
        if (alive && wn !== null) {
          setWhatsNew(wn)
          setOpen(true)
        }
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  if (whatsNew === null) return null

  const dismiss = () => {
    desktop?.whatsNew.dismiss()
    setOpen(false)
  }

  return (
    <Dialog
      open={open}
      onClose={dismiss}
      title={`What’s new in v${whatsNew.toVersion}`}
      className="w-full max-w-md"
    >
      <div className="px-5 py-4">
        <ReleaseNotes notes={whatsNew.notes} />
        <div className="mt-5 flex justify-end">
          <Button variant="primary" onClick={dismiss}>
            Nice
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
