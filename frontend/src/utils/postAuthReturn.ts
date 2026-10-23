// =============================================================================
// AIVIS.ONE Frontend -- Return to the page a visitor came for
// =============================================================================
//
// A visitor who presses "Buy" on the open storefront is sent to registration.
// Registration is followed by the e-mail code (and, for a Telegram sign-in, the
// documents step), so the page the visitor wanted is kept for the length of the
// tab session and opened once the entry steps are done.
//
// Only a path inside the cabinet is kept: it must start with a single "/".
// A public storefront product path is turned into the cabinet's own product
// screen, because a signed-in buyer buys from there.
// =============================================================================

const KEY = 'aivis_return_to'

const PUBLIC_PRODUCT = /^\/public\/products\/([^/?#]+)/

/** A same-origin path, or null. "//host" and "/\host" are not paths. */
export function safeReturnPath(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return null
  return raw
}

/** The cabinet path that stands for a page the visitor was on. */
export function cabinetPathFor(path: string): string {
  const m = PUBLIC_PRODUCT.exec(path)
  if (m) return `/investor/products/${m[1]}`
  return path
}

/** Keeps the page for later. A path that is not safe is dropped. */
export function rememberReturnPath(raw: unknown): void {
  const path = safeReturnPath(raw)
  if (path === null) return
  try {
    sessionStorage.setItem(KEY, cabinetPathFor(path))
  } catch {
    // Storage can be blocked; the visitor then lands on the dashboard.
  }
}

/** Takes the kept page (and forgets it), or null when none was kept. */
export function takeReturnPath(): string | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    sessionStorage.removeItem(KEY)
    return safeReturnPath(raw)
  } catch {
    return null
  }
}

/**
 * Where to go after an entry step (e-mail code, documents). The kept page is
 * opened only once onboarding is complete; before that the guard still has a
 * step to send the visitor to, and the kept page waits.
 */
export function postEntryTarget(onboardingStep: string | undefined): string {
  if (onboardingStep !== 'onboarding_complete') return '/'
  return takeReturnPath() ?? '/'
}
