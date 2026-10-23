// =============================================================================
// AIVIS.ONE Frontend -- Purchases API (Phase F4.2)
// =============================================================================
//
// Typed wrappers for /api/v1/products/{id}/purchase (instant purchase).
// Source of truth: backend/app/modules/purchases/router.py (Sprint 6.1).
//
// One call -> one-shot purchase of the full package. The backend
// returns multiple records when purchase_config.bonuses produces
// gift purchases alongside the sale; consumers iterate the list to
// surface any gifts to the user.
// =============================================================================

import { api } from '@/api/client'
import type { CreatePurchaseRequest, PurchaseResponse } from '@/api/types'

/**
 * POST /api/v1/products/{product_id}/purchase
 *
 * Executes an instant purchase of the full product package for the
 * authenticated investor. Body can be empty (organic) or carry a
 * referral_link_id (Sprint 7.2).
 *
 * Response is a list:
 *   - index 0: the sale purchase (legal_basis='sale')
 *   - indices 1..N: gift purchases from purchase_config.bonuses, if any
 *
 * 4xx conditions the caller must be ready to handle (ApiResponseError):
 *   - 400 "Insufficient balance ..."              -- not enough active confirmed
 *   - 400 "KYC verification required ..."         -- investor.kyc_status != approved
 *   - 400 "Product is not active"                 -- product status changed
 *   - 400 "Company is not active"                 -- company status changed
 *   - 403                                          -- wrong role (only investor/agent)
 *   - 404                                          -- product not found / not active
 */
export function createPurchase(
  productId: string,
  body: CreatePurchaseRequest = {},
): Promise<PurchaseResponse[]> {
  return api.post<PurchaseResponse[]>(`/api/v1/products/${productId}/purchase`, body)
}

/** Gifts granted to the caller that wait for acceptance. */
export interface PendingGiftList {
  items: PurchaseResponse[]
  total: number
}

/**
 * GET /api/v1/purchases/gifts/pending
 *
 * The gifts staff granted to the caller that have not been accepted yet.
 * They credit nothing and are in no portfolio figure until accepted.
 */
export function listPendingGifts(): Promise<PendingGiftList> {
  return api.get<PendingGiftList>('/api/v1/purchases/gifts/pending')
}

/**
 * POST /api/v1/purchases/{id}/accept-gift
 *
 * Accepts one pending gift: the parts are credited at once and the gift
 * becomes an active holding. Answers `kyc_required` (400) when the caller's
 * verification is no longer approved.
 */
export function acceptGift(purchaseId: string): Promise<PurchaseResponse> {
  return api.post<PurchaseResponse>(`/api/v1/purchases/${purchaseId}/accept-gift`)
}
