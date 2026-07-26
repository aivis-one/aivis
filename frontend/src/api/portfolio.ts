// =============================================================================
// AIVIS.ONE Frontend -- Portfolio API (Phase F4.4)
// =============================================================================
//
// Typed wrappers for the investor portfolio endpoints.
// Source of truth: backend/app/modules/portfolio/router.py (Sprint 9.2).
//
// ENDPOINTS WRAPPED:
//   GET /api/v1/portfolio/me                         -- all positions
//   GET /api/v1/portfolio/me/company/{company_id}    -- detail + purchases
//
// PAGINATION:
//   The list endpoint does NOT paginate on the backend -- companies
//   per investor are few enough that sending them all is cheaper
//   than paging ceremony. The detail endpoint DOES paginate the
//   purchases block (page/per_page, defaults 1/20, per_page max 100).
//
// AUTH:
//   Both endpoints require an authenticated user; the backend
//   infers the user_id from the session -- no path param for it.
//
// 404:
//   getCompanyPosition returns 404 when the user has no active
//   purchases in the requested company. Callers (CompanyPositionView)
//   surface this as a graceful empty-state, not an error.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  CompanyPositionDetailResponse,
  PortfolioResponse,
} from '@/api/types'

export interface GetCompanyPositionParams {
  page?: number
  per_page?: number
}

/**
 * GET /api/v1/portfolio/me
 *
 * Returns every company where the caller has active purchases,
 * sorted by current_value_cents descending (done on the backend).
 * Empty positions array for users without purchases -- not 404.
 */
export function getMyPortfolio(): Promise<PortfolioResponse> {
  return api.get<PortfolioResponse>('/api/v1/portfolio/me')
}

/**
 * GET /api/v1/portfolio/me/company/{company_id}
 *
 * Aggregate position in a single company plus a paginated list of
 * the purchases that built it up. 404 when the user has no active
 * purchases in the given company (backend enforces ownership).
 */
export function getCompanyPosition(
  companyId: string,
  params?: GetCompanyPositionParams,
): Promise<CompanyPositionDetailResponse> {
  const qs = buildQueryString({
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<CompanyPositionDetailResponse>(
    `/api/v1/portfolio/me/company/${companyId}${qs}`,
  )
}
