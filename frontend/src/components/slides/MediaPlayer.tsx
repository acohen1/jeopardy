/** MediaPlayer — one video or audio collage cell: media surface + compact
 * transport. Nothing auto-plays. Fullscreen (video only) promotes a wrapper
 * div containing video + transport so the custom controls stay visible. */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Music } from 'lucide-react'
import type { SlideAsset } from '@/types/board'
import { assetUrl } from '@/lib/media'
import { TransportBar } from './TransportBar'
import { clamp01, clampSeekTime, type TimedCellHandle } from './types'

export interface MediaPlayerProps {
  asset: SlideAsset
  boardId: string
  /** Register this cell's playback handle with the owning SlideView. */
  register?: (handle: TimedCellHandle | null) => void
  /** Transport volume remembered across remounts (play overlay Q↔A flips);
   * wins over the default initial volume when present. */
  volumeOverride?: number
  /** Reports user transport-volume drags upward (play overlay persistence). */
  onVolumeChange?: (volume: number) => void
}

export function MediaPlayer({
  asset,
  boardId,
  register,
  volumeOverride,
  onVolumeChange,
}: MediaPlayerProps) {
  const isVideo = asset.asset_type === 'video'
  const mediaRef = useRef<HTMLVideoElement | HTMLAudioElement | null>(null)
  const wrapRef = useRef<HTMLDivElement | null>(null)

  /* Legacy parity: stored asset.volume is a MIXING gain — it only drives
   * video playback. Standalone audio always starts at full volume. */
  const initialVolume = clamp01(volumeOverride ?? (isVideo ? asset.volume : 1))
  const volumeRef = useRef(initialVolume)

  const [playing, setPlaying] = useState(false)
  const [duration, setDuration] = useState(0)
  const [position, setPosition] = useState(0)
  const [volume, setVolume] = useState(initialVolume)
  const [isFs, setIsFs] = useState(false)

  /* Editor live-drag (video only): the stored asset.volume prop flows into
   * the element immediately, without restarting playback. Skipped on mount
   * so a volumeOverride is never clobbered. */
  const skipVolumeSync = useRef(true)
  useEffect(() => {
    if (skipVolumeSync.current) {
      skipVolumeSync.current = false
      return
    }
    if (isVideo) setVolume(clamp01(asset.volume))
  }, [isVideo, asset.volume])
  useEffect(() => {
    volumeRef.current = volume
    const el = mediaRef.current
    if (el && el.volume !== volume) el.volume = volume
  }, [volume])

  const setMediaRef = useCallback((el: HTMLVideoElement | HTMLAudioElement | null) => {
    mediaRef.current = el
    if (el) el.volume = volumeRef.current
  }, [])

  const syncDuration = useCallback(() => {
    const el = mediaRef.current
    if (el && Number.isFinite(el.duration)) setDuration(el.duration)
  }, [])
  const syncPosition = useCallback(() => {
    const el = mediaRef.current
    if (el) setPosition(el.currentTime)
  }, [])

  const toggle = useCallback(() => {
    const el = mediaRef.current
    if (!el) return
    if (el.paused) void el.play().catch(() => {})
    else el.pause()
  }, [])

  const seekTo = useCallback((t: number) => {
    const el = mediaRef.current
    if (!el) return
    const d = Number.isFinite(el.duration) ? el.duration : 0
    const tt = clampSeekTime(t, d)
    el.currentTime = tt
    setPosition(tt)
  }, [])

  const seekBy = useCallback(
    (delta: number) => {
      const el = mediaRef.current
      if (el) seekTo(el.currentTime + delta)
    },
    [seekTo],
  )

  /* Legacy parity: restart = seek 0 AND play. */
  const restart = useCallback(() => {
    const el = mediaRef.current
    if (!el) return
    el.currentTime = 0
    setPosition(0)
    void el.play().catch(() => {})
  }, [])

  const toggleFullscreen = useCallback(() => {
    const w = wrapRef.current
    if (!isVideo || !w) return
    if (document.fullscreenElement === w) void document.exitFullscreen().catch(() => {})
    else void w.requestFullscreen().catch(() => {})
  }, [isVideo])

  useEffect(() => {
    const onChange = () => setIsFs(document.fullscreenElement === wrapRef.current)
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  useEffect(() => {
    if (!register) return
    register({ isVideo, togglePlay: toggle, seekBy, restart, toggleFullscreen })
    return () => register(null)
  }, [register, isVideo, toggle, seekBy, restart, toggleFullscreen])

  /* Unmount: silence immediately. */
  useEffect(() => () => mediaRef.current?.pause(), [])

  const handleVolume = useCallback(
    (v: number) => {
      setVolume(v)
      onVolumeChange?.(v)
    },
    [onVolumeChange],
  )

  const src = assetUrl(boardId, asset.path)
  const mediaEvents = {
    onLoadedMetadata: syncDuration,
    onDurationChange: syncDuration,
    onTimeUpdate: syncPosition,
    onPlay: () => setPlaying(true),
    onPause: () => setPlaying(false),
    onEnded: () => setPlaying(false),
  }

  return (
    <div
      ref={wrapRef}
      className={`flex min-h-0 min-w-0 flex-1 flex-col ${isFs ? 'gap-2 bg-black p-3' : 'gap-1'}`}
    >
      {isVideo ? (
        <div className="relative min-h-0 min-w-0 flex-1">
          <video
            ref={setMediaRef}
            src={src}
            preload="metadata"
            playsInline
            onClick={toggle}
            className="absolute inset-0 h-full w-full cursor-pointer object-contain"
            {...mediaEvents}
          />
        </div>
      ) : (
        <div className="flex min-h-0 min-w-0 flex-1 items-center justify-center">
          <Music className="text-accent" size={52} strokeWidth={1.5} aria-hidden />
          <audio ref={setMediaRef} src={src} preload="metadata" {...mediaEvents} />
        </div>
      )}
      <TransportBar
        playing={playing}
        position={position}
        duration={duration}
        volume={volume}
        onToggle={toggle}
        onSeek={seekTo}
        onRestart={restart}
        onVolume={handleVolume}
        onFullscreen={isVideo ? toggleFullscreen : undefined}
        isFullscreen={isFs}
      />
    </div>
  )
}
