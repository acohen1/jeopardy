/** Tiny global registry of open modal dialogs.
 *
 * While any Dialog is open, page-level bare-key hotkeys (useHotkeys) are
 * suspended so keys like Escape / Space / A close or drive the DIALOG, never
 * the clue overlay or media players behind it. Window keydown listeners fire
 * in registration order, so state — not listener order — has to arbitrate.
 */
let openModals = 0

export function registerModal(): void {
  openModals++
}

export function unregisterModal(): void {
  openModals = Math.max(0, openModals - 1)
}

export function anyModalOpen(): boolean {
  return openModals > 0
}
