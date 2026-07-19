/** Formatting helpers. */

export function money(value: number): string {
  const abs = Math.abs(value).toLocaleString('en-US')
  return value < 0 ? `-$${abs}` : `$${abs}`
}

/** Seconds → m:ss (legacy transport format). */
export function fmtTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const s = Math.floor(seconds)
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

export function truncate(text: string, max: number): string {
  // Slice by code points, not UTF-16 units — string.slice can split an
  // emoji's surrogate pair in half and render mojibake.
  const chars = Array.from(text)
  return chars.length > max ? `${chars.slice(0, max).join('')}…` : text
}
