/** The app's own changelog, baked in at build time.
 *
 * The release build runs from the same commit as RELEASE_NOTES.md, and the
 * shipping procedure guarantees the released version's section exists before
 * a release can build — so the installed app always carries its own notes,
 * offline, forever (unlike the transient post-update What's-New store, which
 * clears on dismissal and never exists for fresh installs).
 */
import raw from '../../../RELEASE_NOTES.md?raw'

/** Body of the changelog section for `version` (e.g. "2.1.0"), or null. */
export function notesForVersion(version: string): string | null {
  // Sections start with "## vX.Y.Z"; everything before the first heading is
  // the instruction comment block.
  const sections = raw.split(/^##\s+/m).slice(1)
  for (const section of sections) {
    const newline = section.indexOf('\n')
    const heading = (newline === -1 ? section : section.slice(0, newline)).trim()
    if (heading === `v${version}`) {
      const body = newline === -1 ? '' : section.slice(newline + 1).trim()
      return body.length > 0 ? body : null
    }
  }
  return null
}
