// =============================================================================
// CBSHOME Frontend -- Public Companies API (Phase F4.1)
// =============================================================================
//
// Typed wrappers for /api/v1/companies/* (public storefront).
// Source of truth: backend/app/modules/companies/router.py.
//
// listCompanies supports ?search= for the storefront filter bottom-sheet
// on the Investor side -- case-insensitive substring match on name,
// with LIKE metacharacters escaped server-side.
// =============================================================================

import { api } from '@/api/client'
import type {
  PublicCompanyDetailResponse,
  PublicCompanyListResponse,
} from '@/api/types'

/**
 * GET /api/v1/companies -- paginated list of active companies.
 *
 * search: optional case-insensitive substring match on company name.
 *         Backend escapes % / _ / \ so the user can type literals.
 */
export function listCompanies(params?: {
  search?: string
  page?: number
  per_page?: number
}): Promise<PublicCompanyListResponse> {
  const q = new URLSearchParams()
  if (params?.search) q.set('search', params.search)
  if (params?.page) q.set('page', String(params.page))
  if (params?.per_page) q.set('per_page', String(params.per_page))
  const qs = q.toString()
  return api.get<PublicCompanyListResponse>(
    `/api/v1/companies${qs ? '?' + qs : ''}`,
  )
}

/**
 * GET /api/v1/companies/{id} -- company detail with roadmap items.
 *
 * Returns 404 for non-active (hidden/archived) companies.
 */
export function getCompany(
  id: string,
): Promise<PublicCompanyDetailResponse> {
  return api.get<PublicCompanyDetailResponse>(`/api/v1/companies/${id}`)
}
