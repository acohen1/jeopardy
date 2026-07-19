/** Small name-prompt dialog shared by "New board" and "Rename". */
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { TextInput } from '@/components/ui/TextInput'

export interface NameDialogProps {
  open: boolean
  title: string
  /** Initial input value each time the dialog opens. */
  initial: string
  submitLabel: string
  busy?: boolean
  onSubmit: (name: string) => void
  onClose: () => void
}

export function NameDialog({
  open,
  title,
  initial,
  submitLabel,
  busy = false,
  onSubmit,
  onClose,
}: NameDialogProps) {
  const [value, setValue] = useState(initial)

  // Reset the field every time the dialog (re)opens.
  useEffect(() => {
    if (open) setValue(initial)
  }, [open, initial])

  const trimmed = value.trim()

  return (
    <Dialog open={open} onClose={onClose} title={title} className="w-full max-w-sm">
      <form
        className="px-5 py-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (trimmed && !busy) onSubmit(trimmed)
        }}
      >
        <TextInput
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoFocus
          onFocus={(e) => e.currentTarget.select()}
          placeholder="Board name"
          aria-label="Board name"
          className="w-full"
        />
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!trimmed || busy}>
            {submitLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  )
}
