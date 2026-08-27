// =============================================================================
// AIVIS.ONE Frontend -- Payments API (H7)
// =============================================================================
//
// Typed wrappers for the INVESTOR-side payment endpoints.
// Source of truth: backend/app/modules/payments/router.py.
//
// ENDPOINTS WRAPPED:
//   POST /api/v1/payments/invoices            -- open a deposit invoice
//   GET  /api/v1/payments/invoices/current    -- the open invoice, if any
//   GET  /api/v1/payments/invoices/{id}       -- one invoice, refreshed
//   POST /api/v1/payments/invoices/{id}/txid  -- submit a transaction hash
//   GET  /api/v1/payments/history             -- paginated payment history
//
// THE BROWSER NEVER TALKS TO THE PAYMENTS SERVICE. Every call here goes
// to this product's own backend, which holds the service token. The ids
// in these paths are the product's row ids, not the service's invoice
// ids -- the latter are not exposed to a browser at all.
//
// NOTE: Staff-side payment endpoints (/api/v1/staff/payments, reverse)
// live in api/admin.ts and must not leak into this module.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  CreateInvoiceRequest,
  InvoiceResponse,
  PaymentHistoryResponse,
  TxidResultResponse,
} from '@/api/types'

/**
 * POST /api/v1/payments/invoices
 *
 * Opens a deposit invoice, or returns the one already open on this
 * network. The amount is ignored in the latter case: an open invoice
 * carries an address and a deadline the user may already have acted on.
 */
export function createInvoice(body: CreateInvoiceRequest): Promise<InvoiceResponse> {
  return api.post<InvoiceResponse>('/api/v1/payments/invoices', body)
}

/**
 * GET /api/v1/payments/invoices/current
 *
 * The user's open invoice on this network, or null when there is none.
 *
 * NULL IS AN ANSWER, NOT A FAILURE. The backend replies 200 with a null
 * body -- callers must branch on it rather than treat a falsy result as
 * an error, or a user with no invoice sees an error screen instead of
 * the amount form.
 */
export function getCurrentInvoice(network: string): Promise<InvoiceResponse | null> {
  const qs = buildQueryString({ network })
  return api.get<InvoiceResponse | null>(`/api/v1/payments/invoices/current${qs}`)
}

/**
 * GET /api/v1/payments/invoices/{id}
 *
 * One invoice as the payments service currently sees it.
 *
 * A terminal status can arrive here before any notification of it does:
 * the service resolves expiry when it is read and emits the matching
 * event afterwards. So this answer being ahead is correct, not a race.
 */
export function getInvoice(invoiceId: string): Promise<InvoiceResponse> {
  return api.get<InvoiceResponse>(`/api/v1/payments/invoices/${invoiceId}`)
}

/**
 * POST /api/v1/payments/invoices/{id}/txid
 *
 * A 200 FROM THIS CALL IS NOT A SUCCESS. It carries a `result_code`
 * that may be `matched` -- or `not_found`, `wrong_address`,
 * `already_used`, `invalid_format` or `api_error`. Rendering the
 * resolved promise as "accepted" is wrong for five of those six.
 *
 * Nor may a caller compute the attempt budget by counting its own
 * submissions: `invalid_format` and `api_error` never reach an explorer
 * and spend nothing. `attempts_remaining` in the response is the only
 * correct source, and it is why the service returns it at all.
 */
export function submitInvoiceTxid(
  invoiceId: string,
  txid: string,
): Promise<TxidResultResponse> {
  return api.post<TxidResultResponse>(
    `/api/v1/payments/invoices/${invoiceId}/txid`,
    { txid },
  )
}

/**
 * GET /api/v1/payments/history
 *
 * Paginated payment history for the authenticated user. Defaults
 * match the backend Query defaults (page=1, per_page=20, max=100).
 */
export function listPaymentHistory(params?: {
  page?: number
  per_page?: number
}): Promise<PaymentHistoryResponse> {
  const qs = buildQueryString({
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<PaymentHistoryResponse>(`/api/v1/payments/history${qs}`)
}
