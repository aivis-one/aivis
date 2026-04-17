// =============================================================================
// CBSHOME Frontend -- Public Products API (Phase F4.1)
// =============================================================================
//
// Typed wrappers for /api/v1/products/* (public storefront).
// Source of truth: backend/app/modules/products/router.py.
// =============================================================================

import { api } from '@/api/client'
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
  const q = new URLSearchParams()
  if (params?.company_id) q.set('company_id', params.company_id)
  if (params?.page) q.set('page', String(params.page))
  if (params?.per_page) q.set('per_page', String(params.per_page))
  const qs = q.toString()
  return api.get<PublicProductListResponse>(
    `/api/v1/products${qs ? '?' + qs : ''}`,
  )
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
