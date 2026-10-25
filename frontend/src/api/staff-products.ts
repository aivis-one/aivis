// =============================================================================
// AIVIS.ONE Frontend -- Staff Products API
// =============================================================================
//
// Typed wrappers for the staff products of a project (backend
// products/staff_router.py and companies/staff_router.py). Creating a product
// needs project_manage AND financial_operations (it shapes what a buyer is
// offered); updating its text and changing its status need project_manage; the
// list of a project's products in every status needs company_manage.
//
//   GET   /api/v1/staff/companies/{id}/products   -- every status, paged
//   POST  /api/v1/staff/products                  -- create
//   PATCH /api/v1/staff/products/{id}             -- text
//   PATCH /api/v1/staff/products/{id}/status      -- hide / archive / return
//
// The cover is a file, not a field of these bodies (H36): api/media.ts.
//
// The status moves the server allows (products/constants.py,
// VALID_PRODUCT_STATUS_TRANSITIONS), mirrored below so the screen offers only
// those: hidden -> active | archived; active -> hidden | archived; archived is
// final.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type { ProductListResponse, ProductResponse } from '@/api/generated'

/** The body of a product creation. `package_size` is the number of parts in one package; it never changes after creation. */
export interface StaffCreateProductRequest {
  company_id: string
  name: string
  description?: string | null
  package_size: number
}

/** The text fields of a product a staff member may change. */
export interface StaffUpdateProductRequest {
  name?: string
  description?: string | null
}

/** The statuses of a product. */
export type StaffProductStatus = 'active' | 'hidden' | 'archived'

/**
 * The statuses a product can move to from `from`; the server's table. An unknown
 * status has no move. Archived is final: no button is offered.
 */
export function allowedProductStatuses(from: string): StaffProductStatus[] {
  if (from === 'active') return ['hidden', 'archived']
  if (from === 'hidden') return ['active', 'archived']
  return []
}

/**
 * GET /api/v1/staff/companies/{id}/products -- one project's products in EVERY
 * status, newest first, paged (per_page at most 100). Needs company_manage.
 */
export function fetchStaffCompanyProducts(
  companyId: string,
  params?: { page?: number; per_page?: number },
): Promise<ProductListResponse> {
  const qs = buildQueryString({ page: params?.page, per_page: params?.per_page })
  return api.get<ProductListResponse>(`/api/v1/staff/companies/${companyId}/products${qs}`)
}

/**
 * POST /api/v1/staff/products -- create a product of a project. The project
 * must have an active pool of parts for sale (409/400 from the server when it
 * has none).
 */
export function createStaffProduct(body: StaffCreateProductRequest): Promise<ProductResponse> {
  return api.post<ProductResponse>('/api/v1/staff/products', body)
}

/** PATCH /api/v1/staff/products/{id} -- change a product's name or description. */
export function updateStaffProduct(
  productId: string,
  body: StaffUpdateProductRequest,
): Promise<ProductResponse> {
  return api.patch<ProductResponse>(`/api/v1/staff/products/${productId}`, body)
}

/**
 * PATCH /api/v1/staff/products/{id}/status -- hide, archive or return a
 * product. Needs project_manage; a move the server does not allow answers 400.
 */
export function updateStaffProductStatus(
  productId: string,
  status: StaffProductStatus,
): Promise<ProductResponse> {
  return api.patch<ProductResponse>(`/api/v1/staff/products/${productId}/status`, { status })
}
