/** StackedAudioPlayer — the stacked-audio collage cell: N hidden, aligned
 * <audio> clips behind ONE transport (instant replacement for the legacy
 * ffmpeg pre-mix). Per-clip volume = its stored asset.volume (live prop
 * updates apply immediately); the transport's volume slider is a master
 * gain over the whole stack. */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Music } from 'lucide-react'
import type { SlideAsset } from '@/types/board'
import { assetUrl } from '@/lib/media'
import { useStackedAudio } from '@/hooks/useStackedAudio'
import { TransportBar } from './TransportBar'
import { clamp01, type TimedCellHandle } from './types'

export interface StackedAudioPlayerProps {
  /** The slide's audio assets, in slide order. */
  clips: SlideAsset[]
  boardId: string
  /** Register this cell's playback handle with the owning SlideView. */
  register?: (handle: TimedCellHandle | null) => void
  /** Master gain remembered across remounts (play overlay Q↔A flips). */
  volumeOverride?: number
  /** Reports user master-volume drags upward (play overlay persistence). */
  onVolumeChange?: (volume: number) => void
}

export function StackedAudioPlayer({
  clips,
  boardId,
  register,
  volumeOverride,
  onVolumeChange,
}: StackedAudioPlayerProps) {
  const stack = useStackedAudio(clips.length)
  const [master, setMaster] = useState(() => clamp01(volumeOverride ?? 1))

  const handleMaster = useCallback(
    (v: number) => {
      setMaster(v)
      onVolumeChange?.(v)
    },
    [onVolumeChange],
  )

  /* Per-clip stored volume × master transport gain, applied live. */
  const { elements } = stack
  useEffect(() => {
    clips.forEach((clip, i) => {
      const el = elements.current[i]
      if (el) el.volume = clamp01(clamp01(clip.volume) * master)
    })
  }, [clips, master, elements])

  const { toggle, seekBy, restart } = stack
  useEffect(() => {
    if (!register) return
    register({ isVideo: false, togglePlay: toggle, seekBy, restart, toggleFullscreen: () => {} })
    return () => register(null)
  }, [register, toggle, seekBy, restart])

  const srcs = useMemo(() => clips.map((c) => assetUrl(boardId, c.path)), [clips, boardId])

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-1">
      <div className="relative flex min-h-0 min-w-0 flex-1 items-center justify-center">
        <Music className="text-accent" size={52} strokeWidth={1.5} aria-hidden />
        <span className="absolute top-1.5 right-1.5 rounded-full border border-line-soft/60 bg-surface-warm/90 px-2 py-0.5 text-[11px] text-ink-muted">
          x{clips.length} stacked
        </span>
        {srcs.map((src, i) => (
          <audio
            key={`${i}:${src}`}
            ref={stack.attach(i)}
            src={src}
            preload="metadata"
            onLoadedMetadata={stack.refresh}
            onDurationChange={stack.refresh}
            onEnded={stack.handleEnded}
          />
        ))}
      </div>
      <TransportBar
        playing={stack.playing}
        position={stack.position}
        duration={stack.duration}
        volume={master}
        onToggle={stack.toggle}
        onSeek={stack.seekTo}
        onRestart={stack.restart}
        onVolume={handleMaster}
      />
    </div>
  )
}
