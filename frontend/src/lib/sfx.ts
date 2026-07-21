/** Game sound effects — synthesized with WebAudio, no assets shipped.
 * The AudioContext is created lazily on the first play (all call sites are
 * user gestures, so autoplay policy is satisfied) and resumed if the browser
 * suspended it. Everything is try/catch'd — audio failure is never an error.
 * Mute persists in localStorage 'sfx-muted'; useSfxMuted() subscribes React
 * components to the flag via useSyncExternalStore. */
import { useSyncExternalStore } from 'react'

export type SfxName = 'pick' | 'correct' | 'wrong' | 'timeUp' | 'fanfare'

// ------------------------------------------------------------------ //
//  Mute state (module-level, persisted, observable)                  //
// ------------------------------------------------------------------ //
const STORAGE_KEY = 'sfx-muted'

let muted: boolean = (() => {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
})()

const listeners = new Set<() => void>()

export function isMuted(): boolean {
  return muted
}

export function setMuted(v: boolean) {
  muted = v
  try {
    localStorage.setItem(STORAGE_KEY, v ? '1' : '0')
  } catch {
    // Persistence is best-effort.
  }
  for (const l of listeners) l()
}

function subscribe(l: () => void): () => void {
  listeners.add(l)
  return () => listeners.delete(l)
}

/** [muted, toggle] — re-renders when the flag changes anywhere in the app. */
export function useSfxMuted(): [boolean, () => void] {
  const m = useSyncExternalStore(subscribe, isMuted)
  return [m, () => setMuted(!muted)]
}

// ------------------------------------------------------------------ //
//  Synthesis                                                         //
// ------------------------------------------------------------------ //
let ctx: AudioContext | null = null

function getCtx(): AudioContext | null {
  try {
    ctx ??= new AudioContext()
    if (ctx.state === 'suspended') void ctx.resume().catch(() => undefined)
    return ctx
  } catch {
    return null
  }
}

interface Tone {
  type: OscillatorType
  /** Start frequency (Hz). */
  freq: number
  /** Optional glide target — exponential ramp over the tone's duration. */
  freqTo?: number
  /** Offset from "now" in seconds. */
  at: number
  /** Length in seconds. */
  dur: number
  /** Peak gain — keep it classy (≤0.15). */
  peak: number
}

function playTone(ac: AudioContext, { type, freq, freqTo, at, dur, peak }: Tone) {
  const t0 = ac.currentTime + at
  const osc = ac.createOscillator()
  const gain = ac.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, t0)
  if (freqTo !== undefined) osc.frequency.exponentialRampToValueAtTime(freqTo, t0 + dur)
  // Fast attack, exponential decay to silence — short and soft, no clicks.
  gain.gain.setValueAtTime(0.0001, t0)
  gain.gain.exponentialRampToValueAtTime(peak, t0 + 0.008)
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur)
  osc.connect(gain).connect(ac.destination)
  osc.start(t0)
  osc.stop(t0 + dur + 0.02)
}

const SOUNDS: Record<SfxName, Tone[]> = {
  /* Quick soft blip when a tile opens. */
  pick: [{ type: 'sine', freq: 880, at: 0, dur: 0.06, peak: 0.1 }],
  /* Bright two-note rise. */
  correct: [
    { type: 'sine', freq: 660, at: 0, dur: 0.09, peak: 0.12 },
    { type: 'sine', freq: 990, at: 0.09, dur: 0.1, peak: 0.12 },
  ],
  /* Descending buzz. */
  wrong: [{ type: 'sawtooth', freq: 220, freqTo: 120, at: 0, dur: 0.25, peak: 0.08 }],
  /* Double beep — same shape as the timer's original inline beep. */
  timeUp: [
    { type: 'sine', freq: 660, at: 0, dur: 0.12, peak: 0.12 },
    { type: 'sine', freq: 520, at: 0.15, dur: 0.12, peak: 0.12 },
  ],
  /* Rising four-note arpeggio (C5-E5-G5-C6), slight overlap, ~700ms. */
  fanfare: [
    { type: 'triangle', freq: 523.25, at: 0, dur: 0.22, peak: 0.11 },
    { type: 'triangle', freq: 659.25, at: 0.13, dur: 0.22, peak: 0.11 },
    { type: 'triangle', freq: 783.99, at: 0.26, dur: 0.22, peak: 0.11 },
    { type: 'triangle', freq: 1046.5, at: 0.39, dur: 0.32, peak: 0.12 },
  ],
}

/** Fire-and-forget; no-ops when muted or when WebAudio is unavailable. */
export function playSfx(name: SfxName) {
  if (muted) return
  try {
    const ac = getCtx()
    if (!ac) return
    for (const tone of SOUNDS[name]) playTone(ac, tone)
  } catch {
    // Audio is decoration — never let it break gameplay.
  }
}
