// =============================================================================
// CBSHOME Frontend -- Withdrawals API (Phase F5.2 B3)
// =============================================================================
//
// Typed wrappers for /api/v1/withdrawals/* (Sprint 6.3).
// Source of truth: backend/app/modules/withdrawals/router.py.
//
// Used by CompanyBalanceView (F5.2 B3 list, F5.2 B4 form) and any
// future role that gains withdrawal access (agents in F6, investors
// when the feature opens up there). The wrappers are role-agnostic
// -- the backend gates withdrawal creation on confirmed passive
// balance, not on role -- so this file does not live under
// /views/company.
//
// PAGINATION.
//   listMyWithdrawals takes optional page/per_page (defaults match the
//   backend: page=1, per_page=20, max=100). Returns
//   WithdrawalListResponse { items, total }.
//
// SCOPE.
//   B3 ships listMyWithdrawals + createWithdrawal in the same file --
//   createWithdrawal stays unused until B4 wires the form. Keeping
//   them together reads cleaner than landing the second wrapper as a
//   one-line patch in B4.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  WithdrawalListResponse,
  WithdrawalResponse,
} from '@/api/types'

/**
 * GET /api/v1/withdrawals/me -- paginated withdrawal history for the
 * authenticated user.
 *
 * Newest-first by created_at on the backend.
 */
export function listMyWithdrawals(params?: {
  page?: number
  per_page?: number
}): Promise<WithdrawalListResponse> {
  const qs = buildQueryString({
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<WithdrawalListResponse>(`/api/v1/withdrawals/me${qs}`)
}

/**
 * POST /api/v1/withdrawals -- request a new withdrawal.
 *
 * Backend instantly debits the passive ledger by `amount_cents`
 * (Sprint 6.3 P6-26) and gates on:
 *   - confirmed passive balance >= amount_cents
 *   - amount_cents within MIN/MAX configured cents
 *   - payout_details set on the user
 *   - no other active withdrawal (pending/confirmed/processing)
 *
 * Errors:
 *   400 -- amount out of bounds, payout_details missing
 *   409 -- another active withdrawal exists, or insufficient balance
 *
 * Returns the newly created WithdrawalResponse with status='pending'.
 */
export function createWithdrawal(
  amount_cents: number,
): Promise<WithdrawalResponse> {
  return api.post<WithdrawalResponse>('/api/v1/withdrawals', {
    amount_cents,
  })
}
