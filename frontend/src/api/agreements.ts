// =============================================================================
// CBSHOME Frontend -- Agreements API
//                       (iter 2.5 R2 §5.5; replaces api/certificates.ts)
// =============================================================================
//
// Typed wrappers for the per-Purchase agreement endpoints and the
// per-investor-company ownership-certificate endpoints. Replaces the
// retired `api/certificates.ts` (iter 2.4 backend removed
// /api/v1/purchases/{id}/certificate without a redirect -- breaking
// change, R2 §5.3).
//
// ENDPOINTS WRAPPED:
//   GET  /api/v1/purchases/{id}/agreement                       (text/html)
//   POST /api/v1/purchases/{id}/agreement/email                 (204)
//   GET  /api/v1/companies/{id}/ownership-certificate           (text/html)
//   POST /api/v1/companies/{id}/ownership-certificate/email     (204)
//
// Source of truth: backend/app/modules/purchases/agreement_router.py
// (R2 §5.3 + §5.4). Both routers live in that file -- per-Purchase
// agreement is a snapshot keyed on `purchase.purchase_agreement_template_id`,
// per-company ownership-certificate is a live aggregate that re-runs
// find_active_template() on each render. Both share the same Jinja2 /
// MinIO / xhtml2pdf machinery.
//
// AUTH:
//   All four endpoints require an authenticated user (any role). The
//   per-Purchase variants additionally check ownership on the backend
//   side and 404 if the caller is not the buyer; the ownership variants
//   404 if the caller has zero active purchases for the requested
//   company. R2 §5.3 also defines 500 as a legitimate response for
//   "template_id NULL on the Purchase row" / "4-stage fallback missed
//   on ownership" -- these are infrastructure errors, not 404 candidates,
//   because in production the platform default guarantees a hit.
//   ERR-11-01 (R2 §5.6): xhtml2pdf failure on already-rendered HTML
//   surfaces as 500 too, not 400.
//
// RATE LIMITING (R2 §5.3):
//   The two POST .../email endpoints are rate-limited per user under
//   Redis keys `agreement_email:{user_id}` and `ownership_email:{user_id}`
//   respectively, both honouring the default auth-flow window
//   (5 / 60s). Callers should expect 429 on rapid retries and render
//   a "try again in a minute" hint -- see iter 2.5 batch 7 wiring in
//   CompanyPositionView / AgreementSheet.
//
// NON-STANDARD CLIENT NOTE (carried from former certificates.ts).
//   The two GET endpoints return text/html, but `api.get` unconditionally
//   parses response.json() and would throw on non-JSON bodies. Rather
//   than bolt a responseType option onto the shared client for two
//   consumers, this module keeps a raw fetch() helper -- _fetchHtmlBlob --
//   that reimplements the bits api.get does NOT do: base URL composition,
//   Authorization header injection, timeout coverage (headers + body
//   phases), and ApiResponseError / ApiNetworkError / ApiTimeoutError
//   mapping. Callers treat thrown errors identically to api.get.
//
//   HTML is returned as a blob URL (createObjectURL) so the consumer
//   (AgreementSheet) can drop it into `<iframe sandbox="" :src="...">`
//   without leaking the auth token into the iframe URL or browser
//   history -- the token lived only in the fetch headers.
//
//   The POST .../email handlers are plain api.post -- 204 No Content,
//   the JSON client is perfectly happy. Callers can `catch (e) { if (e
//   instanceof ApiResponseError && e.status === 429) ... }` for the
//   rate-limit branch.
//
// TIMEOUT COVERAGE.
//   The AbortController arms before fetch() AND stays alive across
//   response.blob(). A network stall in either phase (headers, body
//   download) aborts and maps to ApiTimeoutError. The timer is cleared
//   only in the outer finally, after the blob body has fully arrived
//   (or thrown). This carries forward the B1-post fix from the retired
//   certificates.ts -- removing it would re-introduce the "spinner
//   forever on slow 3G" bug.
//
// LIFECYCLE.
//   createObjectURL() pins the underlying blob until URL.revokeObjectURL().
//   The consumer (useAgreementBlob composable) owns the cleanup
//   pattern -- this module just hands out the URL. Don't call these
//   functions directly from a view; go through useAgreementBlob so
//   onScopeDispose handles the revoke.
//
// PRESIGNED-URL NOTE (foreshadowing R2 §3 attachments, NOT this file).
//   Attachment downloads go through a separate /attachments/{id}/download
//   endpoint that returns 302 to a presigned MinIO URL. See
//   `api/attachments.ts` for that flow; the helper here only deals with
//   inline-rendered HTML.
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

// ---------------------------------------------------------------------------
// Internal: shared raw-fetch helper
// ---------------------------------------------------------------------------

/**
 * Fetch a text/html endpoint and return a blob URL suitable for
 * `<iframe sandbox="" :src>`. Centralises the auth-header injection,
 * timeout coverage, and error-mapping logic shared by every
 * agreement / ownership-certificate GET in this module.
 *
 * Throws ApiResponseError / ApiNetworkError / ApiTimeoutError. Callers
 * should NOT swallow errors at this layer -- the composable wrapper
 * (useAgreementBlob) decides which become inline UI state and which
 * become toasts.
 *
 * Carried forward from former api/certificates.ts (F4.4 B1 + B1-post).
 * Behaviour is byte-for-byte identical to fetchCertificateBlob, only
 * the URL is now a caller-supplied path fragment so we can serve two
 * GETs from one helper.
 */
async function _fetchHtmlBlob(path: string): Promise<string> {
  const url = `${API_BASE_URL}${path}`

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
      // first, fall back to statusText -- callers only need a status-
      // driven discriminant, not the precise text.
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
    // download, the AbortController (still armed) aborts the read
    // and we re-map to ApiTimeoutError below.
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

// ---------------------------------------------------------------------------
// Per-Purchase agreement
// ---------------------------------------------------------------------------

/**
 * GET /api/v1/purchases/{id}/agreement
 *
 * Fetches the per-Purchase agreement HTML (snapshot, keyed on the
 * frozen `purchase.purchase_agreement_template_id`) and returns a
 * blob URL. Backend 404 if the caller is not the buyer; 500 if
 * template_id is NULL (R2 §5.3 -- broken-infra signal, not 404).
 *
 * Use through `useAgreementBlob` so the blob URL is revoked on scope
 * dispose. Caller code in batch 2 (AgreementSheet) does exactly that.
 */
export function fetchAgreementBlob(purchaseId: string): Promise<string> {
  return _fetchHtmlBlob(`/api/v1/purchases/${purchaseId}/agreement`)
}

/**
 * POST /api/v1/purchases/{id}/agreement/email
 *
 * Generates the agreement PDF and emails it to the authenticated
 * investor's address. 204 on success. 404 when the caller does not
 * own the purchase, 429 when rate-limited (`agreement_email:{user_id}`
 * Redis key), 500 when template_id is NULL or PDF rendering fails
 * (ERR-11-01, R2 §5.6). Caller UI maps 429 to a "try again in a
 * minute" hint and 500 to a generic "document temporarily unavailable"
 * toast (see iter 2.5 batch 7 wiring).
 */
export function emailAgreement(purchaseId: string): Promise<void> {
  return api.post<void>(`/api/v1/purchases/${purchaseId}/agreement/email`)
}

// ---------------------------------------------------------------------------
// Per investor-company ownership certificate (live aggregate)
// ---------------------------------------------------------------------------

/**
 * GET /api/v1/companies/{id}/ownership-certificate
 *
 * Renders the live ownership certificate for the (caller, company)
 * pair, aggregating every non-reversed Purchase the caller holds for
 * that company. The template is resolved on each call via the 4-stage
 * fallback (R2 §4.7) -- no snapshot, intentionally.
 *
 * Backend 404 when the company doesn't exist OR the caller has zero
 * active purchases for it; 500 if the template fallback misses across
 * all four stages (which a properly seeded platform default prevents).
 */
export function fetchOwnershipCertificateBlob(
  companyId: string,
): Promise<string> {
  return _fetchHtmlBlob(
    `/api/v1/companies/${companyId}/ownership-certificate`,
  )
}

/**
 * POST /api/v1/companies/{id}/ownership-certificate/email
 *
 * Generates the ownership-certificate PDF and emails it. Same 204 /
 * 404 / 429 / 500 semantics as the agreement variant; rate-limit key
 * is `ownership_email:{user_id}`.
 */
export function emailOwnershipCertificate(
  companyId: string,
): Promise<void> {
  return api.post<void>(
    `/api/v1/companies/${companyId}/ownership-certificate/email`,
  )
}
