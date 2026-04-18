// =============================================================================
// CBSHOME Frontend -- Public Products API (Phase F4.1)
// =============================================================================
//
// Typed wrappers for /api/v1/products/* (public storefront).
// Source of truth: backend/app/modules/products/router.py.
//
// F4.3 B1.1: inline URLSearchParams replaced with buildQueryString
// (TD-F08e closure). No behavioural change -- buildQueryString skips
// the same undefined/null/'' values the inline ternary did.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  PublicProductDetailResponse,
  PublicProductListResponse,
} from '@/api/types'

/**
 * GET /api/v1/products -- paginated list of active products.
 *
 * Optional company_id filter narrows the storefront to one company.
 * Response items carry denormalised company_name / logo / cover so the
 * grid renders without a second round-trip.
 */
export function listProducts(params?: {
  company_id?: string
  page?: number
  per_page?: number
}): Promise<PublicProductListResponse> {
  const qs = buildQueryString({
    company_id: params?.company_id,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<PublicProductListResponse>(`/api/v1/products${qs}`)
}

/**
 * GET /api/v1/products/{id} -- product detail with installment plans.
 *
 * Returns 404 for non-active (hidden/archived) products.
 */
export function getProduct(
  id: string,
): Promise<PublicProductDetailResponse> {
  return api.get<PublicProductDetailResponse>(`/api/v1/products/${id}`)
}
