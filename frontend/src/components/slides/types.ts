/** Shared bits for the slide media layer. */

/**
 * Imperative playback surface a timed cell (video / audio / stacked audio)
 * registers with its owning SlideView so hotkeys can drive the active cell.
 */
export interface TimedCellHandle {
  isVideo: boolean
  togglePlay: () => void
  /** Seek relative by seconds (negative = back). */
  seekBy: (deltaSeconds: number) => void
  /** Legacy parity: seek to 0 AND play. */
  restart: () => void
  /** No-op for audio cells. */
  toggleFullscreen: () => void
}

export function clamp01(v: number): number {
  return Math.min(Math.max(v, 0), 1)
}

/** Clamp a seek target to [0, duration]; while duration is unknown (<= 0)
 * only the lower bound applies. */
export function clampSeekTime(t: number, duration: number): number {
  const bounded = Math.max(t, 0)
  return duration > 0 ? Math.min(bounded, duration) : bounded
}
