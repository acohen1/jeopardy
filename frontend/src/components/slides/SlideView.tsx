/** SlideView — renders a Slide: 1–4 mixed-media collage + optional text.
 *
 * CONTRACT (consumed by the editor preview and the play overlay):
 *  - Collage arrangement mirrors the legacy app: 1 = full, 2 = side-by-side,
 *    3 = two on top + centered half-width third below, 4 = 2×2.
 *  - NOTHING auto-plays, ever. GIFs animate (that's just how <img> works).
 *  - Each video/audio cell gets its own compact transport (MediaPlayer).
 *  - When `audio_stack` is on and 2+ audio assets exist, they collapse into
 *    ONE cell at the FIRST audio's slot with a single transport driving all
 *    clips in sync at their stored volumes — the stacked group is one cell.
 *  - `hotkeys`: Space / ←→ (±1s) / R (restart) / F (video fullscreen) route
 *    to the most-recently-interacted timed cell; a constant-width 2px accent
 *    ring marks the active cell when 2+ timed cells are present.
 *  - Stored volumes are MIXING gains (legacy parity): a video's `volume` is
 *    applied to its player whenever it changes (editor sliders adjust live
 *    playback), stacked clips keep per-clip stored volumes, and standalone
 *    audio always starts its transport at full volume.
 */
import { Fragment, useMemo, useRef, useState } from 'react'
import { ImageOff } from 'lucide-react'
import { MAX_SLIDE_CELLS, type Slide, type SlideAsset } from '@/types/board'
import { assetUrl } from '@/lib/media'
import { useHotkeys } from '@/hooks/useHotkeys'
import { MediaPlayer } from './MediaPlayer'
import { StackedAudioPlayer } from './StackedAudioPlayer'
import type { TimedCellHandle } from './types'

export interface SlideViewProps {
  slide: Slide
  boardId: string
  /** Enable window-level playback hotkeys (play overlay only). */
  hotkeys?: boolean
  /** Transport volumes remembered across remounts, keyed by asset path
   * (stacked cells: clip paths joined with '|'). Play overlay only. */
  volumeOverrides?: ReadonlyMap<string, number>
  /** Reports user transport-volume drags upward, same keying. */
  onVolumeChange?: (assetKey: string, volume: number) => void
  className?: string
}

/** One collage cell — parity with legacy SlideGrid._build_cell_specs. */
type CellSpec =
  | { kind: 'image' | 'gif' | 'video' | 'audio'; asset: SlideAsset }
  | { kind: 'stacked'; clips: SlideAsset[] }

function buildCellSpecs(assets: SlideAsset[], audioStack: boolean): CellSpec[] {
  const audios = assets.filter((a) => a.asset_type === 'audio')
  const doStack = audioStack && audios.length >= 2
  const specs: CellSpec[] = []
  let stackedInserted = false
  for (const a of assets) {
    if (a.asset_type === 'audio' && doStack) {
      if (!stackedInserted) {
        specs.push({ kind: 'stacked', clips: audios }) // at the FIRST audio's slot
        stackedInserted = true
      }
      continue // later audios fold into the stacked cell
    }
    specs.push({ kind: a.asset_type, asset: a })
  }
  return specs.slice(0, MAX_SLIDE_CELLS)
}

function isTimed(spec: CellSpec): boolean {
  return spec.kind === 'video' || spec.kind === 'audio' || spec.kind === 'stacked'
}

function specKey(spec: CellSpec, i: number): string {
  return spec.kind === 'stacked'
    ? `${i}:stacked:${spec.clips.map((c) => c.path).join('|')}`
    : `${i}:${spec.kind}:${spec.asset.path}`
}

/** Type scale for text-only slides — bigger for short quips, calmer for essays. */
function textOnlySize(text: string): string {
  const len = text.trim().length
  if (len <= 80) return 'text-4xl leading-tight font-semibold md:text-5xl'
  if (len <= 200) return 'text-3xl leading-snug font-semibold md:text-4xl'
  if (len <= 400) return 'text-2xl leading-snug md:text-3xl'
  return 'text-xl leading-normal md:text-2xl'
}

/** Image / GIF tile: letterboxed, with a graceful load-error placeholder. */
function ImageCell({ url, name }: { url: string; name: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) {
    return (
      <div className="flex min-h-0 min-w-0 flex-1 flex-col items-center justify-center gap-2 rounded-md bg-surface p-3">
        <ImageOff size={32} className="text-ink-faint" aria-hidden />
        <span className="max-w-full truncate text-xs text-ink-faint">{name}</span>
      </div>
    )
  }
  return (
    <div className="relative min-h-0 min-w-0 flex-1">
      <img
        src={url}
        alt=""
        draggable={false}
        onError={() => setFailed(true)}
        // h/w-full + object-contain scales small media UP to fill the cell
        // (legacy parity: QMovie.setScaledSize always scaled to the target).
        className="absolute inset-0 h-full w-full object-contain"
      />
    </div>
  )
}

export function SlideView({
  slide,
  boardId,
  hotkeys = false,
  volumeOverrides,
  onVolumeChange,
  className,
}: SlideViewProps) {
  const specs = useMemo(
    () => buildCellSpecs(slide.assets, slide.audio_stack),
    [slide.assets, slide.audio_stack],
  )
  const n = specs.length
  const timedIndices = useMemo(
    () => specs.flatMap((s, i) => (isTimed(s) ? [i] : [])),
    [specs],
  )
  const multiTimed = timedIndices.length >= 2

  /* Registry of imperative handles for timed cells, keyed by cell index. */
  const handles = useRef(new Map<number, TimedCellHandle>())
  const registrars = useMemo(
    () =>
      Array.from({ length: n }, (_, i) => (h: TimedCellHandle | null) => {
        if (h) handles.current.set(i, h)
        else handles.current.delete(i)
      }),
    [n],
  )

  /* Active timed cell = most-recently-interacted; default = first timed. */
  const [activeIdx, setActiveIdx] = useState<number | null>(null)
  const active =
    activeIdx != null && timedIndices.includes(activeIdx)
      ? activeIdx
      : (timedIndices[0] ?? null)
  const getActive = () => (active != null ? handles.current.get(active) : undefined)

  useHotkeys(
    {
      ' ': () => getActive()?.togglePlay(),
      ArrowLeft: () => getActive()?.seekBy(-1),
      ArrowRight: () => getActive()?.seekBy(1),
      r: () => getActive()?.restart(),
      f: () => {
        const h = getActive()
        if (h?.isVideo) h.toggleFullscreen()
      },
    },
    { enabled: hotkeys && timedIndices.length > 0 },
  )

  const gridClass =
    n <= 1
      ? 'grid-cols-1 grid-rows-1'
      : n === 2
        ? 'grid-cols-2 grid-rows-1'
        : 'grid-cols-2 grid-rows-2'

  return (
    <div className={`flex min-h-0 min-w-0 flex-col ${className ?? ''}`}>
      {n > 0 && (
        <div className={`grid min-h-0 min-w-0 flex-1 gap-1 ${gridClass}`}>
          {specs.map((spec, i) => {
            const timed = isTimed(spec)
            const thirdOfThree = n === 3 && i === 2
            /* Volume persistence key: asset path (stacked = joined paths). */
            const volumeKey =
              spec.kind === 'stacked'
                ? spec.clips.map((c) => c.path).join('|')
                : spec.asset.path
            const reportVolume = onVolumeChange
              ? (v: number) => onVolumeChange(volumeKey, v)
              : undefined
            /* Constant-width border: only the colour toggles, so activating a
             * cell never reflows the layout (legacy parity). */
            const ringOn = hotkeys && multiTimed && timed && i === active
            const cell = (
              <div
                className={`relative flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border-2 transition-colors duration-150 ${
                  ringOn ? 'border-accent' : 'border-transparent'
                } ${thirdOfThree ? 'w-1/2' : 'w-full'}`}
                onPointerDownCapture={timed ? () => setActiveIdx(i) : undefined}
              >
                {spec.kind === 'stacked' ? (
                  <StackedAudioPlayer
                    clips={spec.clips}
                    boardId={boardId}
                    register={registrars[i]}
                    volumeOverride={volumeOverrides?.get(volumeKey)}
                    onVolumeChange={reportVolume}
                  />
                ) : spec.kind === 'video' || spec.kind === 'audio' ? (
                  <MediaPlayer
                    asset={spec.asset}
                    boardId={boardId}
                    register={registrars[i]}
                    volumeOverride={volumeOverrides?.get(volumeKey)}
                    onVolumeChange={reportVolume}
                  />
                ) : (
                  <ImageCell url={assetUrl(boardId, spec.asset.path)} name={spec.asset.path} />
                )}
              </div>
            )
            /* 3rd of 3 spans both columns but renders centered at half width
             * (legacy CollageWidget / SlideGrid arrangement). */
            return thirdOfThree ? (
              <div key={specKey(spec, i)} className="col-span-2 flex min-h-0 min-w-0 justify-center">
                {cell}
              </div>
            ) : (
              <Fragment key={specKey(spec, i)}>{cell}</Fragment>
            )
          })}
        </div>
      )}
      {slide.text.trim() &&
        (n === 0 ? (
          /* Text-only slide: the text IS the clue — center it and size it
           * like a game show would, scaling down as the text gets longer. */
          <div className="flex min-h-0 flex-1 items-center justify-center p-6">
            <p
              className={`font-display max-w-5xl text-center whitespace-pre-wrap text-ink ${textOnlySize(slide.text)}`}
            >
              {slide.text}
            </p>
          </div>
        ) : (
          <p className="shrink-0 p-3 text-center text-xl whitespace-pre-wrap text-ink">
            {slide.text}
          </p>
        ))}
    </div>
  )
}
