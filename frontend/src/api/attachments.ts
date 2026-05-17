// =============================================================================
// CBSHOME Frontend -- Attachments API
//                       (iter 2.5 R2 §3.3 + §7.1, iter 2.6 R2 §3.4 + §7.2)
// =============================================================================
//
// Typed wrappers for the per-company attachments endpoints.
//
// AUTH-FLOW (iter 2.5):
//   GET /api/v1/companies/{id}/attachments                      (JSON list)
//   GET /api/v1/companies/{id}/attachments/{att_id}/download    (302 -> presigned)
//
// PUBLIC-FLOW (iter 2.6):
//   GET /api/v1/public/companies/{id}/attachments               (JSON list,
//                                                                only public+
//                                                                published rows)
//   GET /api/v1/public/companies/{id}/attachments/{att_id}/download
//                                                               (302 -> presigned,
//                                                                no auth)
//
// Source of truth: backend/app/modules/companies/attachments_router.py
//                  backend/app/modules/companies/attachments_public_router.py
//
// PUBLIC-FLOW VS AUTH-FLOW DIFFERENCES:
//   - listPublicAttachments() does NOT take category / category_prefix /
//     language filters. The public list endpoint exposes them in its
//     signature, but the only public consumer (iter 2.6 PublicAttachments-
//     Section + PublicAttachmentLandingView) does client-side filtering
//     identical to the auth-flow section, so the wrapper stays minimal.
//     If a later consumer needs the server-side filters, extend here.
//   - downloadPublicAttachment() omits the Authorization header even
//     when an auth token happens to be present in the module-level
//     state (e.g. a logged-in user is browsing a public link). The
//     public endpoint does not require it, and dropping it removes the
//     cross-origin header leak on the 302 -> presigned URL hop that the
//     auth-flow TODO still mentions (see AUTH-HEADER-IN-302 NOTE).
//
// DOWNLOAD HELPER (shared):
//   Both downloadAttachment and downloadPublicAttachment go through the
//   internal `_downloadBlob` helper -- fetch + blob materialisation +
//   anchor click + revoke + timeout/error mapping in one place. The
//   public variant passes withAuth=false; the auth variant passes
//   withAuth=true. No public consumer should ever need to call
//   _downloadBlob directly; export it only if a third call site
//   appears.
//
// CONTENT-DISPOSITION NOTE (carried from iter 2.5):
//   Backend sets `Content-Disposition: attachment; filename="..."` on
//   the presigned URL (Round 4 SEC-01 force-download), but Content-
//   Disposition does NOT propagate through blob: URLs -- the browser
//   ignores any header once the response body is in memory. The caller
//   is expected to pass `attachment.original_filename`; without it the
//   browser falls back to the blob URL's UUID, which is ugly but not
//   catastrophic.
//
// AUTH-HEADER-IN-302 NOTE (TODO, auth-flow only):
//   fetch() with redirect: 'follow' (default) forwards the
//   Authorization header on the redirected request, so the presigned
//   MinIO URL receives our Bearer token. MinIO ignores it -- presigned
//   URLs auth via the query string and the Authorization header is just
//   dropped -- but it's still a header leak across origins for the
//   duration of the redirect. The public variant deliberately avoids
//   this by never sending the header. A backend change to return JSON
//   { url } instead of 302 would close the auth-flow caveat too,
//   deferred to a future R2 follow-up since iter 2.6 does not touch
//   backend.
//
// TIMEOUT COVERAGE:
//   Mirrors api/agreements.ts -- AbortController arms before fetch()
//   and stays alive across response.blob(). Both headers-phase and
//   body-phase stalls map to ApiTimeoutError. 30s window for downloads
//   (vs 15s for JSON) -- a large PDF over slow 3G needs the slack.
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
// Auth-flow: List
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
// Public-flow: List (iter 2.6, R2 §3.4)
// ---------------------------------------------------------------------------

/**
 * GET /api/v1/public/companies/{id}/attachments
 *
 * Returns the public + published, non-deleted attachments for a company.
 * No authentication required (the call goes through `api.get`, which
 * attaches `Authorization: Bearer` only when a token is set; for an
 * anonymous visitor no header is sent, for a logged-in visitor the
 * backend silently ignores it).
 *
 * Per-IP rate limit on the backend is 60 req/min (PUBLIC_LIST_RATE_LIMIT,
 * see backend/app/modules/companies/constants.py). On exceeding the
 * limit the call rejects with ApiResponseError(status=429, retryAfter=N).
 */
export function listPublicAttachments(
  companyId: string,
): Promise<AttachmentResponse[]> {
  return api.get<AttachmentResponse[]>(
    `/api/v1/public/companies/${companyId}/attachments`,
  )
}

// ---------------------------------------------------------------------------
// Internal: shared blob-download helper
// ---------------------------------------------------------------------------

/**
 * Fetch an attachment download endpoint, materialise a blob URL,
 * trigger the browser's save-as flow via a synthesised anchor click,
 * then revoke the URL. Shared by the auth-flow and public-flow
 * download wrappers below.
 *
 * `withAuth=true`  -- attach `Authorization: Bearer <token>` if one is
 *                     available (auth-flow download endpoint requires it).
 * `withAuth=false` -- always omit the header (public-flow download
 *                     endpoint does not require it, and omitting closes
 *                     the cross-origin token-leak on the 302 hop to
 *                     the presigned MinIO URL).
 *
 * Throws ApiResponseError / ApiNetworkError / ApiTimeoutError. The
 * caller surfaces the error UX (typically a toast).
 */
async function _downloadBlob(
  url: string,
  filename: string,
  withAuth: boolean,
): Promise<void> {
  const headers: Record<string, string> = {}
  if (withAuth) {
    const token = getAuthToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
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
      // Mirror api.get error surface. Body might be JSON (FastAPI
      // detail envelope) or empty (framework-level error). Try JSON
      // first, fall back to `HTTP <status>` -- callers only need a
      // status-driven discriminant, not the precise text. Retry-After
      // is read on 429 so a download tripped by per-IP rate limit
      // surfaces the right cooldown in the toast.
      let detail = `HTTP ${response.status}`
      try {
        const data = (await response.json()) as {
          detail?: unknown
          message?: unknown
        }
        if (data && typeof data === 'object') {
          if ('detail' in data && data.detail != null) {
            detail = String(data.detail)
          } else if (
            'message' in data
            && typeof data.message === 'string'
          ) {
            detail = data.message
          }
        }
      } catch {
        // Non-JSON body -- keep the `HTTP <status>` default.
      }
      let retryAfter: number | undefined
      if (response.status === 429) {
        const raw = response.headers.get('Retry-After')
        if (raw !== null) {
          const parsed = parseInt(raw, 10)
          if (!Number.isNaN(parsed) && parsed > 0) {
            retryAfter = parsed
          }
        }
      }
      throw new ApiResponseError(response.status, detail, retryAfter)
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

// ---------------------------------------------------------------------------
// Auth-flow: Download
// ---------------------------------------------------------------------------

/**
 * Download an authenticated attachment to the user's device.
 *
 * Fetches the bytes through the auth-flow download endpoint (which
 * 302-redirects to a presigned MinIO URL), materialises a blob URL,
 * clicks a hidden anchor to trigger the browser's save flow, and
 * revokes the URL. Throws on network / HTTP / timeout errors -- the
 * caller renders the toast.
 *
 * filename should be `attachment.original_filename`. See file header
 * for why Content-Disposition does not survive the blob: URL.
 */
export function downloadAttachment(
  companyId: string,
  attachmentId: string,
  filename: string,
): Promise<void> {
  const url =
    `${API_BASE_URL}/api/v1/companies/${companyId}`
    + `/attachments/${attachmentId}/download`
  return _downloadBlob(url, filename, /* withAuth */ true)
}

// ---------------------------------------------------------------------------
// Public-flow: Download (iter 2.6, R2 §3.4)
// ---------------------------------------------------------------------------

/**
 * Download a public attachment to the user's device. No authentication.
 *
 * Backend visibility predicate is `is_public AND is_published AND NOT
 * is_deleted`; anything that fails returns 404 (not 403) to avoid
 * confirming the existence of private files.
 *
 * Per-IP rate limit is 300 req/min (PUBLIC_DOWNLOAD_RATE_LIMIT, see
 * backend/app/modules/companies/constants.py). Independent Redis
 * bucket from the list endpoint, so list spam cannot starve downloads
 * and vice versa.
 */
export function downloadPublicAttachment(
  companyId: string,
  attachmentId: string,
  filename: string,
): Promise<void> {
  const url =
    `${API_BASE_URL}/api/v1/public/companies/${companyId}`
    + `/attachments/${attachmentId}/download`
  return _downloadBlob(url, filename, /* withAuth */ false)
}
