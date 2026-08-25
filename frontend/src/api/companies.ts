// =============================================================================
// AIVIS.ONE Frontend -- Public Companies API
//                       (Phase F4.1 + Sprint 4.5 + iter 2.5 R1 §1.6)
// =============================================================================
//
// Typed wrappers for:
//   - public storefront list / detail (/api/v1/public/companies/*)
//   - Sprint 4.5 authenticated /me              (/api/v1/companies/me)
//
// Source of truth:
//   public list / detail -- backend/app/modules/companies/public_router.py
//   authenticated /me    -- backend/app/modules/companies/router.py
//
// iter 2.5 R1 §1.6 URL MIGRATION:
//   Old paths `/api/v1/companies` and `/api/v1/companies/{id}` were
//   removed in iter 2.4 backend deploy (no 301 redirect -- breaking
//   change, frontend ships its own update synchronously). New paths
//   live under `/api/v1/public/companies/*`, served by the dedicated
//   public router with per-IP rate limiting (60 req/min/IP, R2 §1.6.4).
//
//   `/api/v1/companies/me` (Sprint 4.5) is UNCHANGED -- it's an auth
//   endpoint, not part of the public storefront prefix.
//
// listCompanies supports ?search= for the public storefront --
// case-insensitive substring match on name, with LIKE metacharacters
// escaped server-side.
//
// F4.3 B1.1: inline URLSearchParams replaced with buildQueryString
// (TD-F08e closure). No behavioural change.
//
// Sprint 4.5: +getMyCompany() for the canonical company-side path.
// Phase F5 (Company UI) needs this so a company-role caller can fetch
// its own full profile without going through the public /companies/{id}
// projection (which omits distribution_config and 404s on non-active
// status). Same auth-and-role contract as /company/dashboard and
// /company/analytics: 401 without token, 403 for non-company roles.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  CompanyResponse,
  PublicCompanyDetailResponse,
  PublicCompanyListResponse,
} from '@/api/types'

/**
 * GET /api/v1/public/companies -- paginated list of active companies.
 *
 * Public storefront endpoint. No auth required server-side; the
 * frontend still calls it from authenticated investor flows in
 * iter 2.5 (the public landing page lands in iter 2.6).
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
  return api.get<PublicCompanyListResponse>(`/api/v1/public/companies${qs}`)
}

/**
 * GET /api/v1/companies/me -- authenticated company user's full profile.
 *
 * Sprint 4.5. Canonical path for company-role callers to fetch their
 * own profile. Returns the staff-side `CompanyResponse`, which
 * includes `distribution_config`, `user_id`, and `updated_at` -- all
 * three are stripped from the public `/companies/{id}` projection.
 *
 * Errors:
 *   401 -- missing or invalid Bearer token
 *   403 -- authenticated user has no CompanyProfile (investor / agent /
 *          staff / platform). Same error contract as /company/dashboard.
 *
 * Use this for:
 *   - Company-side Settings (full profile, distribution_config editing)
 *   - Acquiring `company_id` to filter products / drive route guards
 *
 * Do NOT use `getCompany(id)` for the caller's own company -- that
 * endpoint emits the public projection and 404s on non-active status,
 * which means a hidden / archived company can't see its own settings
 * via the public path.
 */
export function getMyCompany(): Promise<CompanyResponse> {
  return api.get<CompanyResponse>('/api/v1/companies/me')
}

/**
 * GET /api/v1/public/companies/{id} -- company detail with stats and
 * roadmap items (R1 §1.6.2 + §5).
 *
 * Returns 404 for non-active (hidden / archived) companies.
 *
 * The response carries `stats` (required, never null) and `roadmap`
 * with the R1 §5 extension (kind, cover_url, post snippet, ...).
 * Investor-side `CompanyOverviewView` (iter 2.5) consumes both inline
 * without a second round-trip.
 */
export function getCompany(id: string): Promise<PublicCompanyDetailResponse> {
  return api.get<PublicCompanyDetailResponse>(`/api/v1/public/companies/${id}`)
}
