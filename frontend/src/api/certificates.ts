// =============================================================================
// CBSHOME Frontend -- Certificates API (Phase F4.4 B1 + B1-post)
// =============================================================================
//
// Typed wrappers for per-purchase certificate endpoints.
// Source of truth: backend/app/modules/purchases/certificate_router.py
// (Sprint 9.2).
//
// ENDPOINTS WRAPPED:
//   GET  /api/v1/purchases/{id}/certificate         -- HTML (Content-Type: text/html)
//   POST /api/v1/purchases/{id}/certificate/email   -- PDF sent to investor email (204)
//
// NON-STANDARD CLIENT NOTE.
//   fetchCertificateBlob() bypasses `api.get` deliberately. The
//   certificate endpoint returns text/html, but api.get unconditionally
//   calls response.json() and would throw on non-JSON bodies. Rather
//   than bolt a responseType option onto the shared client for a
//   single consumer, this module uses a raw fetch() and reimplements
//   the bits it actually needs: base URL, Authorization header,
//   timeout, and the ApiResponseError / ApiNetworkError / ApiTimeoutError
//   taxonomy. Callers treat thrown errors identically to api.get.
//
//   The HTML is returned as a blob URL (createObjectURL) so the
//   consumer CompanyPositionView can drop it into <iframe :src>
//   without leaking the auth token into the iframe's URL or the
//   browser history -- the token lived only in the fetch headers.
//
//   emailCertificate() is plain api.post -- 204 No Content, JSON
//   client is perfectly happy.
//
// TIMEOUT COVERAGE (B1-post fix).
//   B1 armed the abort timer before fetch() and cleared it in the
//   catch block immediately after the response headers arrived.
//   That left response.blob() -- which can be hundreds of KB over
//   a slow 3G link -- unbounded. A stuck download would leave the
//   consumer on a spinner forever. The fix keeps the same
//   AbortController alive across both phases: the timer is cleared
//   only in the outer finally, after the blob body has fully
//   downloaded (or thrown). AbortError is mapped to ApiTimeoutError
//   at either phase so callers keep a single error axis.
//
// LIFECYCLE.
//   createObjectURL() registers the blob with the document. The
//   caller MUST invoke URL.revokeObjectURL(url) when the iframe
//   unmounts / the purchase selection changes / the view closes.
//   Without revoke the blob leaks memory for the page session.
//   The leak is bounded (browser reclaims on navigation) but a
//   long-lived SPA session should not rely on that fallback.
// =============================================================================

import {
  api,
  API_BASE_URL,
  ApiNetworkError,
  ApiResponseError,
  ApiTimeoutError,
  getAuthToken,
} from '@/api/client'

const TIMEOUT_MS = 15_000

/**
 * GET /api/v1/purchases/{id}/certificate
 *
 * Fetches the certificate HTML and returns a blob URL ready for
 * `<iframe :src="...">`. The caller owns the returned URL and is
 * responsible for URL.revokeObjectURL() when it is no longer
 * rendered. Backend returns 404 if the caller is not the purchase
 * owner -- surface that as an empty-state in the UI, not an error
 * toast, since the only way to hit it is a deep-link attempt which
 * the F4.4 UI does not expose.
 *
 * Throws ApiResponseError / ApiNetworkError / ApiTimeoutError to
 * match the surface of api.get -- the caller's error branch can
 * use the same `instanceof ApiResponseError` narrowing it already
 * does for JSON endpoints. ApiTimeoutError fires for both the
 * headers phase (fetch never resolves) and the body phase (blob()
 * stalls) -- the caller does not need to distinguish.
 */
export async function fetchCertificateBlob(purchaseId: string): Promise<string> {
  const url = `${API_BASE_URL}/api/v1/purchases/${purchaseId}/certificate`

  const headers: Record<string, string> = {
    Accept: 'text/html',
  }

  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    let response: Response
    try {
      response = await fetch(url, {
        method: 'GET',
        headers,
        signal: controller.signal,
      })
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiTimeoutError()
      }
      throw new ApiNetworkError(
        err instanceof Error ? err.message : 'Network error',
      )
    }

    if (!response.ok) {
      // Mirror api.get error surface. Body might be JSON (FastAPI
      // detail envelope) or HTML (framework-level error). Try JSON
      // first, fall back to statusText -- the caller only needs a
      // status-driven discriminant, not the precise text.
      let detail = `HTTP ${response.status}`
      try {
        const data = (await response.json()) as { detail?: unknown }
        if (data && typeof data === 'object' && 'detail' in data) {
          detail = String(data.detail)
        }
      } catch {
        // Non-JSON body -- keep the `HTTP <status>` default.
      }
      throw new ApiResponseError(response.status, detail)
    }

    // blob() consumes the body stream. If the network stalls mid-
    // download, the AbortController (still armed) will abort the
    // read and we re-map to ApiTimeoutError below.
    let blob: Blob
    try {
      blob = await response.blob()
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiTimeoutError()
      }
      throw new ApiNetworkError(
        err instanceof Error ? err.message : 'Network error',
      )
    }

    return URL.createObjectURL(blob)
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * POST /api/v1/purchases/{id}/certificate/email
 *
 * Generates a PDF from the certificate template and emails it to
 * the authenticated investor's address. Backend responds 204 on
 * success, 404 when the caller does not own the purchase, and is
 * rate-limited per user to prevent SMTP abuse -- callers should
 * expect the standard 429 shape on rapid retries.
 */
export function emailCertificate(purchaseId: string): Promise<void> {
  return api.post<void>(
    `/api/v1/purchases/${purchaseId}/certificate/email`,
  )
}
