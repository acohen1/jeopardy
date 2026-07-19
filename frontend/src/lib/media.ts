/** Media helpers — extension map mirrors backend EXT_TO_TYPE. */
import type { AssetType } from '@/types/board'

const EXT_TO_TYPE: Record<string, AssetType> = {
  '.gif': 'gif',
  '.png': 'image',
  '.jpg': 'image',
  '.jpeg': 'image',
  '.bmp': 'image',
  '.webp': 'image',
  '.mp4': 'video',
  '.webm': 'video',
  '.mov': 'video',
  '.avi': 'video',
  '.mkv': 'video',
  '.mp3': 'audio',
  '.wav': 'audio',
  '.ogg': 'audio',
  '.flac': 'audio',
  '.aac': 'audio',
}

/** Containers browsers may refuse to play — warn at upload time. */
const RISKY_VIDEO_EXTS = new Set(['.avi', '.mkv', '.mov'])

export function extOf(filename: string): string {
  const i = filename.lastIndexOf('.')
  return i === -1 ? '' : filename.slice(i).toLowerCase()
}

export function extToType(filename: string): AssetType | null {
  return EXT_TO_TYPE[extOf(filename)] ?? null
}

export function isRiskyVideo(filename: string): boolean {
  return RISKY_VIDEO_EXTS.has(extOf(filename))
}

/** Accept attribute for file inputs. */
export const MEDIA_ACCEPT = Object.keys(EXT_TO_TYPE).join(',')

export function assetUrl(boardId: string, path: string): string {
  return `/api/boards/${boardId}/assets/${encodeURIComponent(path)}`
}

/** Default stored volume for a newly added asset (legacy parity). */
export function defaultVolume(assetType: AssetType): number {
  return assetType === 'video' ? 1.0 : 0.3
}
