/** Domain types — mirror backend/app/models.py exactly. */

export type AssetType = 'image' | 'gif' | 'video' | 'audio'

export interface SlideAsset {
  path: string
  asset_type: AssetType
  /** 0–1. Default 0.3 for audio, 1.0 for video. */
  volume: number
}

export interface Slide {
  text: string
  assets: SlideAsset[]
  audio_stack: boolean
}

export interface Cell {
  question_slide: Slide
  answer_slide: Slide
  value: number
  used: boolean
  /** Bonus ("Daily Double") tile — normal-looking on the board, opens with a
   * reveal splash + host wager. */
  bonus: boolean
}

export interface Player {
  name: string
  score: number
}

/** One scoring action, kept on the board for the history feed and undo.
 * `before`/`after` snapshot the player's score around the action. */
export interface ScoreEvent {
  ts: string
  player: string
  kind: 'award' | 'set'
  delta: number
  before: number
  after: number
  /** e.g. "Category 3 · $600" */
  note: string
}

export interface Board {
  id: string
  name: string
  num_cols: number
  num_rows: number
  categories: string[]
  row_values: number[]
  cells: Cell[][]
  allow_negatives: boolean
  players: Player[]
  history: ScoreEvent[]
  created_at: string
  updated_at: string
}

export interface BoardSummary {
  id: string
  name: string
  num_cols: number
  num_rows: number
  filled_cells: number
  total_cells: number
  player_count: number
  updated_at: string
}

export function emptySlide(): Slide {
  return { text: '', assets: [], audio_stack: false }
}

export function emptyCell(value = 0): Cell {
  return { question_slide: emptySlide(), answer_slide: emptySlide(), value, used: false, bonus: false }
}

export function slideIsFilled(slide: Slide): boolean {
  return slide.text.trim().length > 0 || slide.assets.length > 0
}

export function cellIsFilled(cell: Cell): boolean {
  return slideIsFilled(cell.question_slide) || slideIsFilled(cell.answer_slide)
}

/** Authoring gap: a question exists but no answer — worth flagging before
 * someone discovers it live at game night. */
export function cellMissingAnswer(cell: Cell): boolean {
  return slideIsFilled(cell.question_slide) && !slideIsFilled(cell.answer_slide)
}

/**
 * Number of collage cells a slide's assets occupy — a stacked-audio group of
 * 2+ clips collapses into a single cell (mirrors legacy SlideGrid).
 * The hard limit everywhere is 4.
 */
export function slideCellCount(assets: SlideAsset[], audioStack: boolean): number {
  const fixed = assets.filter((a) => a.asset_type !== 'audio').length
  const audio = assets.filter((a) => a.asset_type === 'audio').length
  const audioCells = audioStack && audio >= 2 ? 1 : audio
  return fixed + audioCells
}

export const MAX_SLIDE_CELLS = 4

/**
 * Resize a board in place-copy fashion, preserving existing content —
 * mirrors legacy Board.set_dimensions (pads "Category N" / last value + 200).
 */
export function resizeBoard(board: Board, numRows: number, numCols: number): Board {
  const categories = board.categories.slice(0, numCols)
  while (categories.length < numCols) categories.push(`Category ${categories.length + 1}`)

  const rowValues = board.row_values.slice(0, numRows)
  while (rowValues.length < numRows) {
    // Legacy: last = row_values[-1] if row_values else 200; append(last + 200)
    const last = rowValues.length ? rowValues[rowValues.length - 1] : 200
    rowValues.push(last + 200)
  }

  const cells: Cell[][] = []
  for (let r = 0; r < numRows; r++) {
    const row: Cell[] = []
    for (let c = 0; c < numCols; c++) {
      row.push(board.cells[r]?.[c] ?? emptyCell(rowValues[r]))
    }
    cells.push(row)
  }

  return { ...board, num_rows: numRows, num_cols: numCols, categories, row_values: rowValues, cells }
}
