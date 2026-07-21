/** The app's own changelog, baked in at build time.
 *
 * The release build runs from the same commit as RELEASE_NOTES.md, and the
 * shipping procedure guarantees the released version's section exists before
 * a release can build — so the installed app always carries its own notes,
 * offline, forever (unlike the transient post-update What's-New store, which
 * clears on dismissal and never exists for fresh installs).
 */
import raw from '../../../RELEASE_NOTES.md?raw'

export interface NotesSection {
  version: string
  body: string
}

function parse(): NotesSection[] {
  // Comments are stripped FIRST and headings must be exactly "vX.Y.Z", so a
  // mangled file can never leak instruction text or fake sections into the UI
  // (v2.2.1 shipped with the new section accidentally spliced into the
  // instruction comment block, and the old parser rendered the debris).
  const sections = raw
    .replace(/<!--[\s\S]*?-->/g, '')
    .split(/^##\s+/m)
    .slice(1)
  const out: NotesSection[] = []
  for (const section of sections) {
    const newline = section.indexOf('\n')
    const heading = (newline === -1 ? section : section.slice(0, newline)).trim()
    const body = newline === -1 ? '' : section.slice(newline + 1).trim()
    if (/^v\d+\.\d+\.\d+$/.test(heading) && body.length > 0) {
      out.push({ version: heading.slice(1), body })
    }
  }
  return out
}

/** Every changelog section, newest first (the file's own order). */
export function allNotes(): NotesSection[] {
  return parse()
}

/** Body of the changelog section for `version` (e.g. "2.1.0"), or null. */
export function notesForVersion(version: string): string | null {
  const section = parse().find((s) => s.version === version)
  return section ? section.body : null
}
