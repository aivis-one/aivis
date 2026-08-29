// =============================================================================
// AIVIS.ONE Frontend -- Transactions API (Phase F4.3, TASK-39 item 2)
// =============================================================================
//
// Typed wrappers for the investor transaction event log.
// Source of truth: backend/app/modules/transactions/router.py (Sprint 6.4,
// TASK-39).
//
// ENDPOINTS WRAPPED:
//   GET /api/v1/transactions        -- paginated + filtered list
//   GET /api/v1/transactions/export -- CSV statement download (TASK-39
//                                      item 2, replaces the 501 stub)
//   GET /api/v1/transactions/{id}   -- single event with guard
//
// FILTER SEMANTICS (list AND export -- export takes the same filters,
// minus page/per_page since an export is not paginated):
//   type       -- exact match OR trailing-colon prefix (e.g. "deposit:"
//                 catches every deposit:* event). TransactionsView
//                 category tabs use the prefix form.
//   date_from  -- inclusive ISO-8601 timestamp on created_at
//   date_to    -- inclusive ISO-8601 timestamp on created_at
//   amount_min -- absolute-value lower bound on amount_cents
//   amount_max -- absolute-value upper bound on amount_cents
//
// The full filter surface is wired through even though F4.3 UI only
// drives `type`; date/amount ranges land when the filter sheet is
// added (out of F4.3 scope, see B3 plan decision). The TASK-39 export
// button reuses whatever filter TransactionsView currently has applied
// (today: just `type`, via the category tabs), same scope limit.
//
// EXPORT IS NOT A JSON CALL:
//   api.get() (client.ts) always calls response.json() -- forcing that
//   over a CSV byte stream would throw on every response.
//   downloadTransactionsExport() goes through fetch() directly instead,
//   mirroring api/attachments.ts's _downloadBlob pattern: materialise a blob URL,
//   click a hidden anchor with `download` set, revoke the URL. The one
//   addition vs. that pattern: the filename comes from the server's
//   Content-Disposition header (attachments.ts instead relies on the
//   caller passing attachment.original_filename, since there the file
//   arrives via a 302 to a presigned MinIO URL this client doesn't
//   control the headers of). Reading that header cross-origin needs
//   `Access-Control-Expose-Headers: Content-Disposition` on the
//   backend CORS config -- added in app/main.py alongside this change,
//   since Content-Disposition is not one of the browser's CORS-
//   safelisted response headers by default.
// =============================================================================

import {
  API_BASE_URL,
  ApiNetworkError,
  ApiResponseError,
  ApiTimeoutError,
  api,
  getAuthToken,
  parseRetryAfterHeader,
} from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type { TransactionListResponse, TransactionResponse } from '@/api/types'

const EXPORT_TIMEOUT_MS = 30_000
const EXPORT_FALLBACK_FILENAME = 'transactions_export.csv'

export interface ListTransactionsParams {
  page?: number
  per_page?: number
  // Exact event type (e.g. 'deposit:received') or a trailing-colon
  // prefix (e.g. 'deposit:') -- dispatched on the backend by
  // checking endsWith(':'). Keep as free-form string; enforcing the
  // TransactionType union here would block the prefix form.
  type?: string
  date_from?: string
  date_to?: string
  amount_min?: number
  amount_max?: number
}

/**
 * GET /api/v1/transactions
 *
 * Returns the authenticated user's transaction events, filtered by
 * the caller's params. Each event carries type-specific metadata in
 * `details` which the UI decodes per-type.
 */
export function listTransactions(
  params?: ListTransactionsParams,
): Promise<TransactionListResponse> {
  const qs = buildQueryString({
    page: params?.page,
    per_page: params?.per_page,
    type: params?.type,
    date_from: params?.date_from,
    date_to: params?.date_to,
    amount_min: params?.amount_min,
    amount_max: params?.amount_max,
  })
  return api.get<TransactionListResponse>(`/api/v1/transactions${qs}`)
}

/**
 * GET /api/v1/transactions/{id}
 *
 * Single event detail. Backend enforces `user_id` ownership and
 * returns 404 for events owned by another user.
 */
export function getTransaction(id: string): Promise<TransactionResponse> {
  return api.get<TransactionResponse>(`/api/v1/transactions/${id}`)
}

// ---------------------------------------------------------------------------
// Export (TASK-39 item 2)
// ---------------------------------------------------------------------------

export type ExportTransactionsParams = Omit<ListTransactionsParams, 'page' | 'per_page'>

/**
 * Read filename="..." out of a Content-Disposition: attachment header.
 * Returns null when the header is absent (e.g. CORS didn't expose it,
 * or an old backend build) or carries no quoted filename -- caller
 * falls back to a generic name rather than failing the download.
 */
function _parseExportFilename(response: Response): string | null {
  const raw = response.headers.get('Content-Disposition')
  if (!raw) return null
  const match = /filename="([^"]+)"/.exec(raw)
  return match ? match[1] : null
}

/**
 * GET /api/v1/transactions/export
 *
 * Downloads the authenticated user's transaction history as a CSV
 * file, filtered by the same params ListTransactionsParams accepts
 * minus page/per_page (the backend export is not paginated -- see
 * EXPORT_MAX_ROWS in backend/app/modules/transactions/constants.py
 * for its row cap).
 *
 * Not a JSON call -- see file header for why this bypasses api.get()
 * and goes through fetch() directly, mirroring api/attachments.ts's
 * _downloadBlob helper. Filename is read from the server's
 * Content-Disposition header; if that's ever unavailable (missing
 * header, CORS misconfiguration) falls back to a generic name rather
 * than failing the whole download.
 *
 * Throws:
 *   ApiResponseError -- non-2xx response. status=429 carries
 *     `retryAfter` (seconds) when the backend's Retry-After header
 *     parses; status=400 is the row-cap boundary (see backend
 *     export_transactions_csv() docstring) and carries the human-
 *     readable "N transactions match... narrow the date range" detail
 *     as `.detail`.
 *   ApiNetworkError -- fetch itself failed (offline, DNS, etc.).
 *   ApiTimeoutError -- no response within EXPORT_TIMEOUT_MS.
 *
 * Caller (TransactionsView) is responsible for rendering the failure
 * UX -- this function never swallows an error silently.
 */
export async function downloadTransactionsExport(
  params?: ExportTransactionsParams,
): Promise<void> {
  const qs = buildQueryString({
    type: params?.type,
    date_from: params?.date_from,
    date_to: params?.date_to,
    amount_min: params?.amount_min,
    amount_max: params?.amount_max,
  })
  const url = `${API_BASE_URL}/api/v1/transactions/export${qs}`

  const headers: Record<string, string> = {}
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), EXPORT_TIMEOUT_MS)

  let blobUrl: string | null = null
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
      throw new ApiNetworkError(err instanceof Error ? err.message : 'Network error')
    }

    if (!response.ok) {
      // Mirror api.get's error surface (client.ts) -- FastAPI's
      // {detail: "..."} envelope, or the rate-limiter's {message}
      // shape, falling back to a bare status when the body isn't
      // JSON at all.
      let detail = `HTTP ${response.status}`
      try {
        const data = (await response.json()) as { detail?: unknown; message?: unknown }
        if (data && typeof data === 'object') {
          if ('detail' in data && data.detail != null) {
            detail = String(data.detail)
          } else if ('message' in data && typeof data.message === 'string') {
            detail = data.message
          }
        }
      } catch {
        // Non-JSON body -- keep the `HTTP <status>` default.
      }
      const retryAfter = response.status === 429 ? parseRetryAfterHeader(response) : undefined
      throw new ApiResponseError(response.status, detail, retryAfter)
    }

    let blob: Blob
    try {
      blob = await response.blob()
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiTimeoutError()
      }
      throw new ApiNetworkError(err instanceof Error ? err.message : 'Network error')
    }

    const filename = _parseExportFilename(response) ?? EXPORT_FALLBACK_FILENAME

    blobUrl = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = blobUrl
    anchor.download = filename
    anchor.rel = 'noopener'
    anchor.click()
  } finally {
    clearTimeout(timeoutId)
    if (blobUrl) {
      // Revoke on a microtask boundary -- some browsers need the URL
      // to remain valid for ~1 tick after the click to actually start
      // the download. Same idiom as api/attachments.ts's _downloadBlob.
      setTimeout(() => {
        URL.revokeObjectURL(blobUrl!)
      }, 0)
    }
  }
}
