/** Remembered code+name so rejoining after a refresh is one tap.
 * localStorage access is best-effort (private mode etc.) — never throws. */

const CODE_KEY = 'join-last-code'
const NAME_KEY = 'join-last-name'

export function readLastJoin(): { code: string; name: string } {
  try {
    return {
      code: localStorage.getItem(CODE_KEY) ?? '',
      name: localStorage.getItem(NAME_KEY) ?? '',
    }
  } catch {
    return { code: '', name: '' }
  }
}

export function saveLastJoin(code: string, name: string): void {
  try {
    localStorage.setItem(CODE_KEY, code)
    localStorage.setItem(NAME_KEY, name)
  } catch {
    // Best-effort.
  }
}
