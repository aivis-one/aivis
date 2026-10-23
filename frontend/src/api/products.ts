// =============================================================================
// AIVIS.ONE Frontend -- Public Products API
//                       (Phase F4.1 + iter 2.5 R1 §1.6)
// =============================================================================
//
// Typed wrappers for /api/v1/public/products/* (public storefront).
// Source of truth: backend/app/modules/products/public_router.py.
//
// iter 2.5 R1 §1.6 URL MIGRATION:
//   Old paths `/api/v1/products` and `/api/v1/products/{id}` were
//   removed in iter 2.4 backend deploy (no 301 redirect -- breaking
//   change, frontend ships its own update synchronously). New paths
//   live under `/api/v1/public/products/*`, served by the dedicated
//   public router that shares its per-IP rate-limit budget with
//   `/api/v1/public/companies/*` (60 req/min/IP combined, R2 §1.6.4).
//
//   The auth-only POST `/api/v1/products/{id}/purchase` is wrapped in
//   `api/purchases.ts`, not here -- it is NOT under the public prefix
//   and was untouched by iter 2.4.
//
// F4.3 B1.1: inline URLSearchParams replaced with buildQueryString
// (TD-F08e closure). No behavioural change -- buildQueryString skips
// the same undefined/null/'' values the inline ternary did.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type { PublicProductDetailResponse, PublicProductListResponse } from '@/api/types'

/**
 * GET /api/v1/public/products -- paginated list of active products.
 *
 * Public storefront endpoint. No auth required server-side; in iter 2.5
 * called from the authenticated ProductsByCompany view (scoped to one
 * company via company_id), the public landing page lands in iter 2.6.
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
  return api.get<PublicProductListResponse>(`/api/v1/public/products${qs}`)
}

/**
 * GET /api/v1/public/products/{id} -- product detail with installment
 * plans.
 *
 * Returns 404 for non-active (hidden / archived) products.
 */
export function getProduct(id: string): Promise<PublicProductDetailResponse> {
  return api.get<PublicProductDetailResponse>(`/api/v1/public/products/${id}`)
}

/** Bonus parts one package brings the caller if bought now. */
export interface PurchasePreview {
  bonus_units: number
  bonus_percent: number
}

/**
 * GET /api/v1/products/{id}/purchase-preview -- the bonus parts one
 * package of the product brings the signed-in buyer right now,
 * computed by the server by the same rule the purchase applies.
 */
export function getPurchasePreview(id: string): Promise<PurchasePreview> {
  return api.get<PurchasePreview>(`/api/v1/products/${encodeURIComponent(id)}/purchase-preview`)
}

/** One product of the signed-in project, every status (staff-managed fields included). */
export interface OwnProductResponse {
  id: string
  company_id: string
  name: string
  description: string | null
  package_size: number
  cover_url: string | null
  price_per_unit_cents: number
  status: string
  created_at: string
  updated_at: string | null
}

export interface OwnProductListResponse {
  items: OwnProductResponse[]
  total: number
  page: number
  per_page: number
}

/**
 * GET /api/v1/company/products -- the signed-in project's own products,
 * every status (active, hidden, archived). Project accounts only.
 */
export function listMyProducts(params?: {
  page?: number
  per_page?: number
}): Promise<OwnProductListResponse> {
  const qs = buildQueryString({ page: params?.page, per_page: params?.per_page })
  return api.get<OwnProductListResponse>(`/api/v1/company/products${qs}`)
}
