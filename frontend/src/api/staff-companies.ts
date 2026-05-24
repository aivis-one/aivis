// =============================================================================
// CBSHOME Frontend -- Staff Companies API (iter 2.7 Block B)
// =============================================================================
//
// Typed wrappers for /api/v1/staff/companies/* (backend
// companies/staff_router.py). Distinct from api/companies.ts, which
// speaks the PUBLIC storefront surface (/api/v1/public/companies) plus
// the company-role self endpoint (/api/v1/companies/me). The staff
// surface returns every company regardless of status and carries
// distribution_config -- it requires the company_manage permission
// server-side.
//
// This module starts with the read surfaces the Platform tab needs in
// Block B (list) and Block C (price history). The write surfaces
// (create / update / price change / roadmap CRUD) land in Block C / D
// alongside the views that drive them, to avoid shipping unused
// client code ahead of its consumer.
//
// Endpoints covered here:
//   GET /api/v1/staff/companies                     -- list (paginated)
//   GET /api/v1/staff/companies/{id}/price-history  -- price history (B3)
//
// Endpoints deferred to Block C / D:
//   POST   /api/v1/staff/companies
//   PATCH  /api/v1/staff/companies/{id}
//   PATCH  /api/v1/staff/companies/{id}/price
//   POST   /api/v1/staff/companies/{id}/roadmap
//   PATCH  /api/v1/staff/companies/{id}/roadmap/{item_id}
//   DELETE /api/v1/staff/companies/{id}/roadmap/{item_id}
//   PATCH  /api/v1/staff/companies/{id}/roadmap/reorder
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  CompanyListResponse,
  PriceHistoryListResponse,
} from '@/api/types'

/**
 * GET /api/v1/staff/companies -- paginated company list, all statuses.
 *
 * Filters (all optional, combinable):
 *   - status: 'active' | 'hidden' | 'archived' (backend CompanyStatus
 *             StrEnum, 422 on any other value). Sent on the wire as
 *             `?status=` -- the backend binds it under that alias even
 *             though the Python identifier is `company_status`.
 *   - search: case-insensitive substring on company name (backend
 *             escapes %, _, \ so literals match)
 *
 * When status is omitted the staff list returns every status (the
 * service forces active_only=false), unlike the public list which is
 * active-only.
 *
 * Pagination: page (1-indexed), per_page (1..100).
 */
export function fetchStaffCompanies(params?: {
  status?: 'active' | 'hidden' | 'archived'
  search?: string
  page?: number
  per_page?: number
}): Promise<CompanyListResponse> {
  const qs = buildQueryString({
    status: params?.status,
    search: params?.search,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<CompanyListResponse>(`/api/v1/staff/companies${qs}`)
}

/**
 * GET /api/v1/staff/companies/{id}/price-history -- immutable price
 * change log for one company, newest-first (iter 2.6c B3).
 *
 * 404 on an unknown company_id (delivered by the service's get_company,
 * so a probe for an invalid id can't leak existence via an empty 200).
 *
 * Pagination uses the same envelope as the list endpoint.
 */
export function fetchStaffCompanyPriceHistory(
  companyId: string,
  params?: {
    page?: number
    per_page?: number
  },
): Promise<PriceHistoryListResponse> {
  const qs = buildQueryString({
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<PriceHistoryListResponse>(
    `/api/v1/staff/companies/${companyId}/price-history${qs}`,
  )
}
