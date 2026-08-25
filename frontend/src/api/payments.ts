// =============================================================================
// AIVIS.ONE Frontend -- Payments API (Phase F4.3)
// =============================================================================
//
// Typed wrappers for the INVESTOR-side payment endpoints.
// Source of truth: backend/app/modules/payments/router.py (Sprint 5.2).
//
// ENDPOINTS WRAPPED:
//   POST /api/v1/payments/crypto-address -- get or create deposit address
//   GET  /api/v1/payments/history        -- paginated payment history
//
// NOTE: Staff-side payment endpoints (/api/v1/staff/payments, reverse)
// live in api/admin.ts and must not leak into this module.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  CreateAddressRequest,
  DepositAddressResponse,
  PaymentHistoryResponse,
} from '@/api/types'

/**
 * POST /api/v1/payments/crypto-address
 *
 * Idempotent: backend returns the user's existing address for the
 * given network if one exists, otherwise generates a stub address.
 * F4.3 hardcodes network='TRC20'; the network selector is deferred.
 */
export function createCryptoAddress(body: CreateAddressRequest): Promise<DepositAddressResponse> {
  return api.post<DepositAddressResponse>('/api/v1/payments/crypto-address', body)
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
