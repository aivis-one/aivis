// =============================================================================
// AIVIS.ONE Frontend -- Staff Products API
// =============================================================================
//
// Typed wrappers for /api/v1/staff/products (backend products/staff_router.py).
// Creating a product needs project_manage AND financial_operations (it shapes
// what a buyer is offered); updating its text needs project_manage.
//
// WHAT IS NOT HERE, and why. There is no staff READ of a project's products:
// the list a staff member sees is the storefront's (GET /public/products), which
// carries the active products only. So the staff screen creates a product and
// edits an active one's text, and offers no status change -- a product taken
// off sale would drop out of the only list the screen has and could not be
// found again. The status endpoint (PATCH /staff/products/{id}/status) waits
// for a staff list that shows every status.
// =============================================================================

import { api } from '@/api/client'
import type { ProductResponse } from '@/api/generated'

/** The body of a product creation. `package_size` is the number of parts in one package; it never changes after creation. */
export interface StaffCreateProductRequest {
  company_id: string
  name: string
  description?: string | null
  package_size: number
  cover_url?: string | null
}

/** The text fields of a product a staff member may change. */
export interface StaffUpdateProductRequest {
  name?: string
  description?: string | null
  cover_url?: string | null
}

/**
 * POST /api/v1/staff/products -- create a product of a project. The project
 * must have an active pool of parts for sale (409/400 from the server when it
 * has none).
 */
export function createStaffProduct(body: StaffCreateProductRequest): Promise<ProductResponse> {
  return api.post<ProductResponse>('/api/v1/staff/products', body)
}

/** PATCH /api/v1/staff/products/{id} -- change a product's name, description or cover. */
export function updateStaffProduct(
  productId: string,
  body: StaffUpdateProductRequest,
): Promise<ProductResponse> {
  return api.patch<ProductResponse>(`/api/v1/staff/products/${productId}`, body)
}
