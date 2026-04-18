// =============================================================================
// CBSHOME Frontend -- Transactions API (Phase F4.3)
// =============================================================================
//
// Typed wrappers for the investor transaction event log.
// Source of truth: backend/app/modules/transactions/router.py (Sprint 6.4).
//
// ENDPOINTS WRAPPED:
//   GET /api/v1/transactions        -- paginated + filtered list
//   GET /api/v1/transactions/{id}   -- single event with guard
//
// FILTER SEMANTICS:
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
// added (out of F4.3 scope, see B3 plan decision).
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  TransactionListResponse,
  TransactionResponse,
} from '@/api/types'

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
