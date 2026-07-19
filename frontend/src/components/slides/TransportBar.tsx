/** TransportBar — compact transport controls shared by every timed cell:
 * play/pause, restart, seek (live scrub), time, volume, optional fullscreen.
 * Dark translucent surface, ~h-9, mirrors the legacy compact _ControlsBar. */
import type { ReactNode } from 'react'
import { Maximize2, Minimize2, Pause, Play, RotateCcw, Volume2 } from 'lucide-react'
import { fmtTime } from '@/lib/format'

export interface TransportBarProps {
  playing: boolean
  /** Current position in seconds. */
  position: number
  /** Duration in seconds (0 while metadata loads). */
  duration: number
  /** Playback volume 0–1 shown on the volume slider. */
  volume: number
  onToggle: () => void
  onSeek: (seconds: number) => void
  onRestart: () => void
  onVolume: (volume: number) => void
  /** Present → a fullscreen toggle is shown (video cells only). */
  onFullscreen?: () => void
  isFullscreen?: boolean
  className?: string
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(e) => {
        // Blur so a later Space hotkey never re-triggers this button.
        e.currentTarget.blur()
        onClick()
      }}
      className="flex size-7 shrink-0 items-center justify-center rounded-md text-ink-muted transition-colors duration-100 hover:bg-white/10 hover:text-ink"
    >
      {children}
    </button>
  )
}

export function TransportBar({
  playing,
  position,
  duration,
  volume,
  onToggle,
  onSeek,
  onRestart,
  onVolume,
  onFullscreen,
  isFullscreen = false,
  className,
}: TransportBarProps) {
  return (
    <div
      className={`flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-line-soft/60 bg-bg-deep/85 px-2 backdrop-blur-sm ${className ?? ''}`}
    >
      <IconButton label={playing ? 'Pause (Space)' : 'Play (Space)'} onClick={onToggle}>
        {playing ? <Pause size={15} /> : <Play size={15} />}
      </IconButton>
      <IconButton label="Restart (R)" onClick={onRestart}>
        <RotateCcw size={14} />
      </IconButton>
      <div className="min-w-6 flex-1">
        <input
          type="range"
          aria-label="Seek"
          min={0}
          max={Math.max(duration, 0.01)}
          step={0.05}
          value={Math.min(position, Math.max(duration, 0))}
          onChange={(e) => onSeek(Number(e.target.value))}
          onPointerUp={(e) => e.currentTarget.blur()}
        />
      </div>
      <span className="shrink-0 text-[11px] whitespace-nowrap text-ink-muted tabular-nums">
        {fmtTime(position)} / {fmtTime(duration)}
      </span>
      <div className="flex shrink-0 items-center gap-1">
        <Volume2 size={13} className="text-ink-faint" aria-hidden />
        <div className="w-14">
          <input
            type="range"
            aria-label="Volume"
            min={0}
            max={1}
            step={0.01}
            value={volume}
            onChange={(e) => onVolume(Number(e.target.value))}
            onPointerUp={(e) => e.currentTarget.blur()}
          />
        </div>
      </div>
      {onFullscreen && (
        <IconButton
          label={isFullscreen ? 'Exit fullscreen (F / Esc)' : 'Fullscreen (F)'}
          onClick={onFullscreen}
        >
          {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </IconButton>
      )}
    </div>
  )
}
