/** Tiny release-notes renderer shared by AboutDialog and WhatsNewDialog.
 *
 * No markdown library: lines are split; "#"-prefixed lines render as small
 * headings (RELEASE_NOTES.md leads with "## v2.2.0"), "- " lines become
 * styled bullets, everything else renders as a plain paragraph.
 */

export function ReleaseNotes({ notes }: { notes: string }) {
  const lines = notes
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)

  if (lines.length === 0) return null

  return (
    <div className="space-y-1.5 text-sm leading-relaxed">
      {lines.map((line, i) => {
        const heading = /^#{1,6}\s+(.*)$/.exec(line)
        if (heading) {
          return (
            <p key={i} className="font-display text-accent-bright pt-1 text-xs font-bold tracking-wide">
              {heading[1]}
            </p>
          )
        }
        return line.startsWith('- ') ? (
          <div key={i} className="text-ink-muted flex gap-2">
            <span aria-hidden className="text-accent select-none">
              •
            </span>
            <span className="min-w-0">{line.slice(2)}</span>
          </div>
        ) : (
          <p key={i} className="text-ink">
            {line}
          </p>
        )
      })}
    </div>
  )
}
