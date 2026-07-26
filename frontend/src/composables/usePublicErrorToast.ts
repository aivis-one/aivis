// =============================================================================
// AIVIS.ONE Frontend -- usePublicErrorToast Composable (iter 2.6 Block C1)
// =============================================================================
//
// Centralised rate-limit toast handler for public-flow views. Every
// public endpoint (storefront list, company detail, product detail,
// attachments list / download) shares a per-IP rate-limit budget on
// the backend; when exceeded, the API client throws ApiResponseError
// with status=429 and a parsed Retry-After value (api/client.ts,
// Batch 1).
//
// CONTRACT.
//   const { notifyRateLimit } = usePublicErrorToast()
//
//   try {
//     await listCompanies(...)
//   } catch (err) {
//     if (notifyRateLimit(err)) return       // 429 handled by toast
//     errored.value = true                    // other errors -> inline UI
//   }
//
//   - Returns true when `err` was a 429 and a toast has been shown.
//   - Returns false for any other shape; caller falls through to its
//     own error handling (inline error banner, retry button, etc).
//
// WHY ONLY 429.
//   The auth-flow has a generic "showToast on any thrown error" pattern,
//   but the public-flow already has inline error UI on every view
//   (errored ref + retry button). Doubling that with a toast for
//   every 5xx is noisy. 429 is special because:
//
//   1. It is per-IP, transient (the visitor will succeed in N seconds),
//      and not actionable by the caller's UI -- no "retry now" button
//      helps; the visitor must wait.
//   2. The Retry-After hint is information the inline error UI cannot
//      surface without timer logic in every view.
//
//   So the helper handles 429 with a transient toast, and leaves
//   every other status to the caller's inline UI.
//
// MESSAGE CHOICE.
//   - retryAfter is a positive int  -> `public.errors.rateLimit` with
//     {seconds} placeholder, e.g. "Too many requests. Try again in 42
//     seconds."
//   - retryAfter missing or invalid -> `public.errors.rateLimitGeneric`,
//     e.g. "Too many requests. Try again in a minute."
//
//   The fallback closes the "Retry-After header is missing / 0 /
//   negative" gap that the iter 2.6 prompt called out explicitly.
//   Without the guard we would render "Try again in NaN seconds" or
//   similar.
// =============================================================================

import { useI18n } from 'vue-i18n'

import { ApiResponseError } from '@/api/client'
import { useToast } from '@/composables/useToast'

export function usePublicErrorToast() {
  const { t } = useI18n()
  const { showToast } = useToast()

  /**
   * Inspect an error caught from a public-flow API call. If it is a
   * 429 rate-limit response, surface a toast and return true; otherwise
   * return false and leave the caller to its own error path.
   *
   * The helper does NOT swallow the error -- it only decides whether
   * to render the 429 toast. The caller still gets to inspect `err`
   * after notifyRateLimit returns false (e.g. distinguish 404 from 5xx
   * for inline empty-state vs retry banner).
   *
   * @param err - the value caught from a try/catch around the API call.
   * @returns true if `err` was a 429 (toast shown); false otherwise.
   */
  function notifyRateLimit(err: unknown): boolean {
    if (!(err instanceof ApiResponseError)) return false
    if (err.status !== 429) return false

    const seconds = err.retryAfter
    if (typeof seconds === 'number' && seconds > 0) {
      showToast(t('public.errors.rateLimit', { seconds }), 'warning')
    } else {
      // Retry-After header missing, malformed, or non-positive. Use
      // the generic copy so the user does not see "NaN seconds".
      showToast(t('public.errors.rateLimitGeneric'), 'warning')
    }
    return true
  }

  return { notifyRateLimit }
}
