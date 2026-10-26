// =============================================================================
// AIVIS.ONE Frontend -- the website sign-in through Telegram: the mark (H45)
// =============================================================================
//
// On the website the person signs in with "Log In With Telegram" (OpenID
// Connect; backend/app/modules/auth/web_login.py):
//   start   -> the backend hands out Telegram's URL and a `state`; this
//              browser keeps { state, mark } (the MARK is random, made here)
//              and goes to Telegram;
//   return  -> Telegram sends the browser back to RETURN_PATH with `code` and
//              `state` (or `error`); TelegramReturnView reads them once,
//              wipes them from the address bar, and completes the sign-in
//              only if this browser holds a mark for that very state.
//
// WHY THE MARK (login CSRF): a return link made by someone else -- their own
// Telegram, stopped at the return -- must not sign THIS browser into THEIR
// account. Such a link arrives in a browser with no mark (or a mark for another
// state) and is refused here, without a request; the backend checks the same
// mark again before it exchanges the code.
//
// WHERE THE MARK LIVES: localStorage. The person leaves for the Telegram app
// and comes back; a new tab of the same browser must still find it
// (sessionStorage is per tab). It is one-time: taken (read and removed) at the
// first return, whatever the outcome.
// =============================================================================

/** Where Telegram sends the browser back, inside the cabinet (router base
 *  included by the router). The same literal is RETURN_PATH in
 *  backend/app/modules/auth/web_login.py. */
export const RETURN_PATH = '/auth/telegram/return'

/** localStorage key of the started sign-in's mark. */
export const LOGIN_MARK_KEY = 'aivis_telegram_login_mark'

/** A started sign-in, as this browser remembers it. */
export interface LoginMark {
  state: string
  mark: string
}

/** 32 random bytes, base64url -- 43 characters, within the backend's 32..128. */
export function newMark(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

/** Remember the sign-in this browser is about to start. */
export function rememberLoginMark(mark: LoginMark): void {
  try {
    localStorage.setItem(LOGIN_MARK_KEY, JSON.stringify(mark))
  } catch {
    // Unwritable storage: the return finds no mark and is refused -- the
    // safe direction.
  }
}

/** The remembered sign-in, removed as it is read. Garbage reads as none. */
export function takeLoginMark(): LoginMark | null {
  let raw: string | null
  try {
    raw = localStorage.getItem(LOGIN_MARK_KEY)
    localStorage.removeItem(LOGIN_MARK_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  try {
    const value: unknown = JSON.parse(raw)
    if (value !== null && typeof value === 'object') {
      const { state, mark } = value as Record<string, unknown>
      if (typeof state === 'string' && state && typeof mark === 'string' && mark) {
        return { state, mark }
      }
    }
  } catch {
    // Not JSON: no mark.
  }
  return null
}
