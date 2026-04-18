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
//
// F4.3 B1.1: inline URLSearchParams replaced with buildQueryString
// (TD-F08e closure). No behavioural change.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
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
  const qs = buildQueryString({
    search: params?.search,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<PublicCompanyListResponse>(`/api/v1/companies${qs}`)
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
