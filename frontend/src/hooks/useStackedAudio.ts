/** useStackedAudio — one virtual transport driving N <audio> elements in
 * sync (the web replacement for the legacy ffmpeg pre-mix, but instant).
 *
 *  - duration = LONGEST clip; position tracks the longest clip.
 *  - play starts all clips aligned; clips shorter than the current position
 *    stay ended/silent. Pause pauses all. Seek sets every clip's currentTime
 *    (clamped to its own duration).
 *  - Nothing auto-plays. The consumer renders the <audio> elements and wires
 *    `attach(i)` as each ref plus refresh/handleEnded as events; per-clip
 *    volume is applied by the consumer directly on `elements.current[i]`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { clampSeekTime } from '@/components/slides/types'

const EPS = 0.05
/** Max drift from the lead clip before the playback poll re-aligns a clip. */
const DRIFT = 0.35

export interface StackedAudio {
  /** The live <audio> elements, index-aligned with the clip list. */
  elements: { current: (HTMLAudioElement | null)[] }
  /** Stable ref callback for clip i. */
  attach: (index: number) => (el: HTMLAudioElement | null) => void
  playing: boolean
  /** Longest clip's duration, seconds. */
  duration: number
  /** Position along the longest clip, seconds. */
  position: number
  /** Wire to onLoadedMetadata / onDurationChange of every clip. */
  refresh: () => void
  /** Wire to onEnded of every clip. */
  handleEnded: () => void
  toggle: () => void
  play: () => void
  pause: () => void
  seekTo: (seconds: number) => void
  seekBy: (deltaSeconds: number) => void
  /** Legacy parity: seek 0 AND play. */
  restart: () => void
}

export function useStackedAudio(count: number): StackedAudio {
  const elements = useRef<(HTMLAudioElement | null)[]>([])
  const detachers = useRef<((() => void) | undefined)[]>([])
  /** Seek targets for clips whose metadata hasn't loaded yet — applied on
   * that clip's loadedmetadata instead of clamping to 0 / pausing it. */
  const pendingSeeks = useRef<(number | null)[]>([])
  const playingRef = useRef(false)
  const positionRef = useRef(0)
  const [playing, setPlayingState] = useState(false)
  const [duration, setDuration] = useState(0)
  const [position, setPositionState] = useState(0)

  const setPlaying = useCallback((p: boolean) => {
    playingRef.current = p
    setPlayingState(p)
  }, [])
  const setPosition = useCallback((t: number) => {
    positionRef.current = t
    setPositionState(t)
  }, [])

  const els = useCallback(
    () => elements.current.filter((el): el is HTMLAudioElement => el != null),
    [],
  )

  const maxDuration = useCallback(() => {
    let max = 0
    for (const el of els()) if (Number.isFinite(el.duration)) max = Math.max(max, el.duration)
    return max
  }, [els])

  const longest = useCallback(() => {
    let best: HTMLAudioElement | null = null
    let bestDur = -1
    for (const el of els()) {
      const d = Number.isFinite(el.duration) ? el.duration : 0
      if (d > bestDur) {
        bestDur = d
        best = el
      }
    }
    return best
  }, [els])

  /* Out-of-band pause/play (media keys, device switch, OS focus stealing):
   * mirror the elements' real state back into `playing`. */
  const syncPlayingFromEls = useCallback(() => {
    const list = els()
    if (!list.length) return
    const anyPlaying = list.some((el) => !el.paused)
    if (anyPlaying !== playingRef.current) setPlaying(anyPlaying)
  }, [els, setPlaying])

  const attachers = useMemo(
    () =>
      Array.from({ length: count }, (_, i) => (el: HTMLAudioElement | null) => {
        detachers.current[i]?.()
        detachers.current[i] = undefined
        elements.current[i] = el
        if (!el) return
        const onLoadedMetadata = () => {
          const t = pendingSeeks.current[i]
          if (t == null) return
          pendingSeeks.current[i] = null
          const d = Number.isFinite(el.duration) ? el.duration : 0
          el.currentTime = Math.min(t, d)
          if (playingRef.current) {
            if (t < d - EPS) void el.play().catch(() => {})
            else el.pause()
          }
        }
        const onPlayPause = () => syncPlayingFromEls()
        el.addEventListener('loadedmetadata', onLoadedMetadata)
        el.addEventListener('play', onPlayPause)
        el.addEventListener('pause', onPlayPause)
        detachers.current[i] = () => {
          el.removeEventListener('loadedmetadata', onLoadedMetadata)
          el.removeEventListener('play', onPlayPause)
          el.removeEventListener('pause', onPlayPause)
        }
      }),
    [count, syncPlayingFromEls],
  )
  const attach = useCallback((i: number) => attachers[i], [attachers])

  const refresh = useCallback(() => setDuration(maxDuration()), [maxDuration])

  const play = useCallback(() => {
    const list = els()
    if (!list.length) return
    const dmax = maxDuration()
    const lead = longest()
    let start = lead ? lead.currentTime : 0
    if (dmax > 0 && start >= dmax - EPS) start = 0 // everything finished → restart from 0
    elements.current.forEach((el, i) => {
      if (!el) return
      const d = Number.isFinite(el.duration) ? el.duration : 0
      if (d === 0) {
        // Metadata still loading: start it now, align once metadata arrives.
        if (start > 0) pendingSeeks.current[i] = start
        void el.play().catch(() => {})
        return
      }
      const t = Math.min(start, d)
      el.currentTime = t // always align every clip to the transport position
      if (t < d - EPS) void el.play().catch(() => {})
    })
    setPosition(start)
    setPlaying(true)
  }, [els, longest, maxDuration, setPlaying, setPosition])

  const pause = useCallback(() => {
    for (const el of els()) el.pause()
    setPlaying(false)
  }, [els, setPlaying])

  const toggle = useCallback(() => {
    if (playingRef.current) pause()
    else play()
  }, [pause, play])

  const seekTo = useCallback(
    (t: number) => {
      const tt = clampSeekTime(t, maxDuration())
      elements.current.forEach((el, i) => {
        if (!el) return
        const d = Number.isFinite(el.duration) ? el.duration : 0
        if (d === 0) {
          // Metadata not loaded yet: defer the seek to its loadedmetadata.
          pendingSeeks.current[i] = tt
          return
        }
        pendingSeeks.current[i] = null
        el.currentTime = Math.min(tt, d)
        if (playingRef.current) {
          // Seeking back can revive an ended clip; past its end it stays silent.
          if (tt < d - EPS) void el.play().catch(() => {})
          else el.pause()
        }
      })
      setPosition(tt)
    },
    [maxDuration, setPosition],
  )

  const seekBy = useCallback(
    (delta: number) => seekTo(positionRef.current + delta),
    [seekTo],
  )

  const restart = useCallback(() => {
    seekTo(0)
    play()
  }, [play, seekTo])

  const handleEnded = useCallback(() => {
    const list = els()
    if (!list.length) return
    const allDone = list.every((el) => {
      const d = Number.isFinite(el.duration) ? el.duration : 0
      return el.ended || el.currentTime >= d - EPS
    })
    if (allDone) {
      setPlaying(false)
      setPosition(maxDuration())
    }
  }, [els, maxDuration, setPlaying, setPosition])

  /* Position poll while playing (legacy polls at 300ms), doubling as the
   * drift re-sync: any clip more than DRIFT off the lead is re-aligned. */
  useEffect(() => {
    if (!playing) return
    const id = window.setInterval(() => {
      const lead = longest()
      if (!lead) return
      const t = lead.currentTime
      setPosition(t)
      for (const el of els()) {
        if (el === lead) continue
        const d = Number.isFinite(el.duration) ? el.duration : 0
        if (d === 0) continue
        const target = Math.min(t, d)
        if (target < d - EPS && Math.abs(el.currentTime - target) > DRIFT) {
          el.currentTime = target
        }
      }
    }, 250)
    return () => window.clearInterval(id)
  }, [playing, els, longest, setPosition])

  /* Unmount: silence everything. */
  useEffect(
    () => () => {
      for (const el of elements.current) el?.pause()
    },
    [],
  )

  return {
    elements,
    attach,
    playing,
    duration,
    position,
    refresh,
    handleEnded,
    toggle,
    play,
    pause,
    seekTo,
    seekBy,
    restart,
  }
}
