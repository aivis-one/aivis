// =============================================================================
// AIVIS.ONE Frontend -- Attachments API
//                       (iter 2.5 R2 §3.3 + §7.1, iter 2.6 R2 §3.4 + §7.2,
//                        H32 P-121 download as a navigation)
// =============================================================================
//
// Typed wrappers for the per-company attachments endpoints.
//
// AUTH-FLOW (iter 2.5):
//   GET /api/v1/companies/{id}/attachments                      (JSON list)
//   GET /api/v1/companies/{id}/attachments/{att_id}/download    (JSON link)
//
// PUBLIC-FLOW (iter 2.6):
//   GET /api/v1/public/companies/{id}/attachments               (JSON list,
//                                                                only public+
//                                                                published rows)
//   GET /api/v1/public/companies/{id}/attachments/{att_id}/download
//                                                               (JSON link,
//                                                                no auth)
//
// Source of truth: backend/app/modules/companies/attachments_router.py
//                  backend/app/modules/companies/attachments_public_router.py
//
// DOWNLOAD IS A NAVIGATION (H32 P-121):
//   Both download endpoints return { url, ttl_seconds } -- a presigned
//   link on the public storage address (https://files.aivis.one) -- and
//   the browser is sent to it with location.assign(). The link carries
//   response-content-disposition=attachment with the original filename,
//   so the browser saves the file and stays on the page; an SVG/HTML
//   payload is never rendered (Round 4 SEC-01). This replaced a fetch()
//   that followed a 302 across origins into a blob: URL: that needed CORS
//   on the storage, carried the Authorization header through the
//   redirect, lost Content-Disposition inside the blob, and could not
//   work at all while the link pointed at the internal storage address.
//   KYC documents already open the same way (StaffUsersView.vue).
//
// PUBLIC-FLOW VS AUTH-FLOW DIFFERENCES:
//   - listPublicAttachments() does NOT take category / category_prefix /
//     language filters. The public list endpoint exposes them in its
//     signature, but the only public consumer (iter 2.6 PublicAttachments-
//     Section + PublicAttachmentLandingView) does client-side filtering
//     identical to the auth-flow section, so the wrapper stays minimal.
//     If a later consumer needs the server-side filters, extend here.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type { AttachmentDownloadURLResponse, AttachmentResponse } from '@/api/types'

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
  return api.get<AttachmentResponse[]>(`/api/v1/companies/${companyId}/attachments${qs}`)
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
export function listPublicAttachments(companyId: string): Promise<AttachmentResponse[]> {
  return api.get<AttachmentResponse[]>(`/api/v1/public/companies/${companyId}/attachments`)
}

// ---------------------------------------------------------------------------
// Download: ask for the link, then go to it
// ---------------------------------------------------------------------------

/**
 * Send the browser to a presigned download link.
 *
 * A navigation, not a fetch: the response is an attachment, so the
 * browser saves it under the name in Content-Disposition and the current
 * page stays.
 */
export function openDownloadLink(url: string): void {
  window.location.assign(url)
}

/**
 * Download an authenticated attachment.
 *
 * Asks the auth-flow endpoint for the link (the API client sends the
 * session as with any call) and opens it. Throws the API client's errors
 * (ApiResponseError / ApiNetworkError / ApiTimeoutError) -- the caller
 * renders the toast.
 */
export async function downloadAttachment(companyId: string, attachmentId: string): Promise<void> {
  const link = await api.get<AttachmentDownloadURLResponse>(
    `/api/v1/companies/${companyId}/attachments/${attachmentId}/download`,
  )
  openDownloadLink(link.url)
}

/**
 * Download a public attachment. No authentication required.
 *
 * Backend visibility predicate is `is_public AND is_published AND NOT
 * is_deleted`; anything that fails returns 404 (not 403) to avoid
 * confirming the existence of private files. Per-IP rate limit is
 * PUBLIC_DOWNLOAD_RATE_LIMIT (backend/app/modules/companies/constants.py),
 * a bucket independent of the list endpoint.
 */
export async function downloadPublicAttachment(
  companyId: string,
  attachmentId: string,
): Promise<void> {
  const link = await api.get<AttachmentDownloadURLResponse>(
    `/api/v1/public/companies/${companyId}/attachments/${attachmentId}/download`,
  )
  openDownloadLink(link.url)
}
