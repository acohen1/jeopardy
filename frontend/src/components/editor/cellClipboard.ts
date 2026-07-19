/** Module-level clipboard for editor cell copy/paste. Plain module state (not
 * React state) so the copied cell survives SPA navigation — copy on one board,
 * paste on another within the same session. */
import type { Slide } from '@/types/board'

interface ClipboardCell {
  question_slide: Slide
  answer_slide: Slide
  /** Board the copy came from — pasting into a different board may reference
   * media files the target board lacks (missing-media placeholder renders). */
  sourceBoardId: string
}

let slot: ClipboardCell | null = null

/** Slides are plain JSON data — a JSON round-trip is a safe deep clone. */
const cloneSlide = (slide: Slide): Slide => JSON.parse(JSON.stringify(slide)) as Slide

/** Store deep clones of the cell's slides (value/used are never copied). */
export function setClipboardCell(question: Slide, answer: Slide, sourceBoardId: string): void {
  slot = { question_slide: cloneSlide(question), answer_slide: cloneSlide(answer), sourceBoardId }
}

/** Fresh deep clones per call so pasted cells never share references with the
 * clipboard slot or with each other. */
export function getClipboardCell(): ClipboardCell | null {
  if (!slot) return null
  return {
    question_slide: cloneSlide(slot.question_slide),
    answer_slide: cloneSlide(slot.answer_slide),
    sourceBoardId: slot.sourceBoardId,
  }
}

export function hasClipboardCell(): boolean {
  return slot !== null
}
