/** Typed contract for the Electron preload bridge (window.jeopardy).
 *
 * THE source of truth shared by the Electron shell (desktop/preload.cjs must
 * implement exactly this shape) and the frontend update UX. In a plain
 * browser (npm run dev, LAN TV view) `desktop` is undefined and every
 * desktop-only surface must hide itself.
 */

export type UpdateState =
  | { phase: 'idle' }
  | { phase: 'checking' }
  | { phase: 'up-to-date' }
  | { phase: 'downloading'; percent: number }
  | { phase: 'ready'; version: string; notes: string }
  | { phase: 'error'; message: string }

export interface WhatsNew {
  fromVersion: string
  toVersion: string
  /** Release notes (markdown-ish plain text from the GitHub release body). */
  notes: string
}

export interface DesktopBridge {
  /** Installed app version, e.g. "2.1.0". */
  appVersion: string
  updates: {
    getState(): Promise<UpdateState>
    /** Manual re-check (auto-check runs on launch + periodically). */
    check(): void
    /** Quit and install the downloaded update. */
    restartToUpdate(): void
    /** Subscribe to state changes; returns an unsubscribe fn. */
    onState(cb: (state: UpdateState) => void): () => void
  }
  whatsNew: {
    /** Non-null exactly once after an update, until dismissed. */
    get(): Promise<WhatsNew | null>
    dismiss(): void
  }
  /** Fires after a .jeopardy file double-click was imported by the shell. */
  onImported(cb: (boardId: string) => void): () => void
  storage: {
    /** Current data directory + how many boards live there. */
    getInfo(): Promise<{ path: string; boardCount: number; isDefault: boolean }>
    /** Reveal the data directory in Explorer. */
    openFolder(): void
    /**
     * Native folder picker → optionally migrate the current library →
     * persist → respawn the sidecar at the new location → reload the app.
     * Resolves null if the user cancelled.
     */
    choose(): Promise<{ path: string } | null>
    /** Reset to the default (%APPDATA%/Chaewon Jeopardy) and respawn. */
    resetToDefault(): Promise<void>
  }
  lan: {
    /** Whether wifi devices may open the app, and the URLs they'd use. */
    get(): Promise<{ enabled: boolean; urls: string[] }>
    /** Toggle LAN access (rebinds the server; Windows may show a firewall prompt). */
    set(enabled: boolean): Promise<void>
  }
}

export const desktop: DesktopBridge | undefined = (
  window as unknown as { jeopardy?: DesktopBridge }
).jeopardy

export const isDesktop = desktop !== undefined
