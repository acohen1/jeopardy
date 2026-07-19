/** Keyboard-shortcuts reference — opened with `?` anywhere, or the floating
 * keyboard button. All app hotkeys are bare keys (never Ctrl/Alt/Win chords,
 * except Ctrl+S which shadows the browser's useless save dialog), are ignored
 * while typing in a field, and suspend while any dialog is open — so nothing
 * here can fight Windows or the browser. */
import { Keyboard } from 'lucide-react'

import { Dialog } from './Dialog'

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="bg-surface text-ink border-line inline-flex h-[22px] min-w-[22px] items-center justify-center rounded-md border border-b-2 px-1.5 font-sans text-[11px] font-semibold">
      {children}
    </kbd>
  )
}

interface Row {
  keys: React.ReactNode[]
  label: string
}

function Section({ title, rows }: { title: string; rows: Row[] }) {
  return (
    <section>
      <h3 className="text-accent mb-2 text-[11px] font-bold tracking-widest uppercase">
        {title}
      </h3>
      <ul className="space-y-1.5">
        {rows.map((row, i) => (
          <li key={i} className="flex items-center justify-between gap-4">
            <span className="text-ink-muted text-[13px]">{row.label}</span>
            <span className="flex shrink-0 items-center gap-1">
              {row.keys.map((k, j) => (
                <Kbd key={j}>{k}</Kbd>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function HotkeysDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="Keyboard shortcuts" className="w-full max-w-2xl">
      <div className="grid gap-x-10 gap-y-6 px-6 py-5 sm:grid-cols-2">
        <Section
          title="Clue overlay"
          rows={[
            { keys: ['A'], label: 'Reveal the answer' },
            { keys: ['Q'], label: 'Back to the question' },
            { keys: ['T'], label: 'Start / restart the timer' },
            { keys: ['Esc'], label: 'Close the clue' },
          ]}
        />
        <Section
          title="Media playback"
          rows={[
            { keys: ['Space'], label: 'Play / pause' },
            { keys: ['←', '→'], label: 'Seek ±1 second' },
            { keys: ['R'], label: 'Restart the clip' },
            { keys: ['F'], label: 'Video fullscreen' },
          ]}
        />
        <Section
          title="Play mode"
          rows={[
            { keys: ['P'], label: 'Present mode (TV fullscreen)' },
            { keys: ['Shift', '/'], label: 'This help (types "?") — works anywhere' },
          ]}
        />
        <Section
          title="Editor"
          rows={[
            { keys: ['Ctrl', 'S'], label: 'Save now' },
            { keys: ['Ctrl', 'V'], label: 'Paste media into a cell' },
            { keys: ['Enter'], label: 'Confirm dialogs & inline edits' },
            { keys: ['Esc'], label: 'Close dialog (asks if unsaved)' },
          ]}
        />
      </div>

      <div className="border-line-soft bg-surface/40 border-t px-6 py-4">
        <h3 className="text-accent mb-2 text-[11px] font-bold tracking-widest uppercase">
          Mouse tricks
        </h3>
        <ul className="text-ink-muted grid gap-x-10 gap-y-1 text-[13px] sm:grid-cols-2">
          <li>
            <b className="text-ink font-semibold">Right-click a board cell</b> — Review / Reset
            (play) · Copy / Paste / Clear / Swap (editor)
          </li>
          <li>
            <b className="text-ink font-semibold">Click a score</b> — edit it directly (host
            corrections)
          </li>
          <li>
            <b className="text-ink font-semibold">Right-click the timer</b> — pick 10 / 20 / 30 /
            60 seconds
          </li>
          <li>
            <b className="text-ink font-semibold">Right-click a library card</b> — rename,
            duplicate, export, delete
          </li>
          <li>
            <b className="text-ink font-semibold">Click a clip</b> — make it the target of the
            playback keys
          </li>
          <li>
            <b className="text-ink font-semibold">Drag &amp; drop / paste files</b> — add media in
            the cell editor
          </li>
        </ul>
      </div>

      <p className="text-ink-faint flex items-center gap-1.5 px-6 pb-4 text-[11px]">
        <Keyboard size={13} aria-hidden />
        Shortcuts pause while you're typing or a dialog is open — they never clash with browser or
        Windows keys.
      </p>
    </Dialog>
  )
}
