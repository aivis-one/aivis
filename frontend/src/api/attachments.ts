// =============================================================================
// CBSHOME Frontend -- Attachments API (iter 2.5 R2 §3.3 + §7.1)
// =============================================================================
//
// Typed wrappers for the per-company attachments endpoints consumed by
// the Investor `CompanyOverviewView` documents section (R2 §7.1). The
// backend endpoints landed in iter 2.2; the frontend simply did not
// call them until this iteration -- this module is brand new.
//
// ENDPOINTS WRAPPED:
//   GET /api/v1/companies/{id}/attachments                      (JSON list)
//   GET /api/v1/companies/{id}/attachments/{att_id}/download    (302 -> presigned)
//
// Source of truth: backend/app/modules/companies/attachments_router.py
// (R2 §3.3, iter 2.2). Public-flow variant (no-auth, public-only) lives
// under /api/v1/public/companies/... and is wired in iter 2.6, NOT here.
//
// AUTH:
//   Both endpoints require an authenticated user (any role). The list
//   returns only is_published=True AND is_deleted=False rows -- private
//   metadata never reaches the wire. Filters (category / category_prefix
//   / language) are exact-match or LIKE prefix% on the backend.
//
// LIST: SHAPE.
//   AttachmentResponse hides storage_key / created_by / is_deleted; we
//   re-export the type from generated.ts via api/types.ts so views
//   import from one canonical place.
//
// DOWNLOAD: IMPERATIVE FUNCTION.
//   downloadAttachment is fire-and-forget from the caller's point of
//   view: it fetches the bytes, materialises a blob URL, clicks a
//   hidden anchor with `download={filename}` to trigger the browser's
//   save-as / open-in-viewer flow, and revokes the URL. No state is
//   exposed to Vue -- the caller awaits the promise and renders any
//   error itself (toast).
//
//   WHY NOT window.location.assign(authEndpoint)?
//     The backend endpoint requires Authorization: Bearer, and a top-
//     level navigation does NOT carry that header. The browser would
//     hit /download anonymously and get 401. fetch() with the header
//     is the only way to authenticate the redirect from JS.
//
//   WHY NOT `<a href="${API}/...">` styling?
//     Same reason -- the anchor click is a navigation, no Authorization
//     header. We need to fetch first, get bytes, THEN materialise a
//     same-origin blob: URL the anchor can hit.
//
//   FILENAME ARGUMENT.
//     Backend sets Content-Disposition: attachment; filename="..." (R2
//     §3.3 Round 4 SEC-01 force-download), but Content-Disposition does
//     NOT propagate through blob: URLs -- the browser ignores any header
//     once the response body is in memory. The caller is expected to
//     pass `attachment.original_filename` from the AttachmentResponse
//     it already holds; without it the browser falls back to the blob
//     URL's UUID, which is ugly but not catastrophic.
//
//   AUTH-HEADER-IN-302 NOTE (TODO).
//     fetch() with redirect: 'follow' (default) forwards the
//     Authorization header on the redirected request, so the
//     presigned MinIO URL receives our Bearer token. MinIO ignores
//     it -- presigned URLs auth via the query string and the
//     Authorization header is just dropped -- but it's still a
//     header leak across origins for the duration of the redirect.
//     Switching to redirect: 'manual' would close that, but then
//     the response is opaqueredirect and Location is unreadable
//     from JS -- a dead end. The cleanest fix is a backend change
//     to return JSON { url } instead of 302, deferred to a future
//     R2 follow-up since iter 2.5 does not touch backend.
//
// TIMEOUT COVERAGE.
//   Mirrors api/agreements.ts -- AbortController arms before fetch()
//   and stays alive across response.blob(). Both headers-phase and
//   body-phase stalls map to ApiTimeoutError. 15s window matches the
//   shared client default.
// =============================================================================

import {
  API_BASE_URL,
  ApiNetworkError,
  ApiResponseError,
  ApiTimeoutError,
  api,
  getAuthToken,
} from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type { AttachmentResponse } from '@/api/types'

const DOWNLOAD_TIMEOUT_MS = 30_000

// ---------------------------------------------------------------------------
// List
// ---------------------------------------------------------------------------

/**
 * GET /api/v1/companies/{id}/attachments
 *
 * Returns the published, non-deleted attachments for a company.
 * Optional filters narrow the result set on the backend:
 *
 *   category        -- exact path-tree match (e.g. 'legal/licenses/business')
 *   category_prefix -- LIKE prefix% (e.g. 'legal/')
 *   language        -- ISO 639-1 exact match. Column is NOT NULL since
 *                      migration 0034; every row has a language.
 *
 * The Investor CompanyOverview section consumes the unfiltered list and
 * does L1-grouping client-side via attachment.category.split('/')[0].
 */
export function listAttachments(
  companyId: string,
  params?: {
    category?: string
    category_prefix?: string
    language?: string
  },
): Promise<AttachmentResponse[]> {
  const qs = buildQueryString({
    category: params?.category,
    category_prefix: params?.category_prefix,
    language: params?.language,
  })
  return api.get<AttachmentResponse[]>(
    `/api/v1/companies/${companyId}/attachments${qs}`,
  )
}

// ---------------------------------------------------------------------------
// Download (imperative)
// ---------------------------------------------------------------------------

/**
 * Download an attachment to the user's device.
 *
 * Fetches the bytes through the auth-flow download endpoint (which
 * 302-redirects to a presigned MinIO URL), materialises a blob URL,
 * clicks a hidden anchor to trigger the browser's save flow, and
 * revokes the URL. Throws on network / HTTP / timeout errors -- the
 * caller renders the toast.
 *
 * Returns a Promise<void>; there is no value to surface, only success
 * or failure. The save-as dialog appears synchronously inside the
 * anchor click; the promise resolves once cleanup is done.
 *
 * filename should be `attachment.original_filename`. See file header
 * for why Content-Disposition does not survive the blob: URL.
 */
export async function downloadAttachment(
  companyId: string,
  attachmentId: string,
  filename: string,
): Promise<void> {
  const url =
    `${API_BASE_URL}/api/v1/companies/${companyId}` +
    `/attachments/${attachmentId}/download`

  const headers: Record<string, string> = {}
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(
    () => controller.abort(),
    DOWNLOAD_TIMEOUT_MS,
  )

  let blobUrl: string | null = null
  try {
    let response: Response
    try {
      response = await fetch(url, {
        method: 'GET',
        headers,
        signal: controller.signal,
        // redirect: 'follow' is the default; we want fetch() to walk
        // through the 302 onto the presigned MinIO URL automatically.
        // See file header for the auth-header-on-redirect caveat.
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
      // Mirror api.get error surface.
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

    blobUrl = URL.createObjectURL(blob)

    // Synthesise the click. Anchor is detached from the DOM (no need
    // to append for the click to fire in modern browsers); the
    // browser's save-as / open-in-viewer flow handles the rest.
    const anchor = document.createElement('a')
    anchor.href = blobUrl
    anchor.download = filename
    // rel="noopener" is irrelevant for a blob: URL but keeps the
    // anchor congruent with general security hygiene.
    anchor.rel = 'noopener'
    anchor.click()
  } finally {
    clearTimeout(timeoutId)
    if (blobUrl) {
      // Revoke on a microtask boundary -- some browsers need the URL
      // to remain valid for ~1 tick after the click to actually
      // start the download. setTimeout(0) is the canonical idiom.
      setTimeout(() => {
        URL.revokeObjectURL(blobUrl!)
      }, 0)
    }
  }
}
