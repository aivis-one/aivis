// =============================================================================
// CBSHOME Frontend -- Company API (Phase F5.1)
// =============================================================================
//
// Typed wrappers for the company-side dashboard + analytics endpoints.
// Source of truth: backend/app/modules/company_dashboard/router.py
//   - Sprint 4.3 B5  -- initial endpoints
//   - Sprint 4.6     -- installment_tranche aggregation hotfix
//
// ENDPOINTS WRAPPED:
//   GET /api/v1/company/dashboard    -- aggregated dashboard payload
//   GET /api/v1/company/analytics    -- analytics (sales-by-month + by-product)
//
// FILE NAMING.
//   This module is `company.ts` (singular) and is distinct from
//   `companies.ts` (plural). The plural file mirrors the backend
//   `companies` module (public storefront + `/companies/me` profile);
//   this file mirrors the backend `company_dashboard` module
//   (specialised company-role dashboard + analytics). Keeping the
//   split aligned with the backend boundary makes the source-of-truth
//   trail trivial to follow.
//
// AUTH.
//   Both endpoints sit behind `get_current_company_profile` on the
//   backend, which returns 403 for any caller that does not have a
//   `CompanyProfile` row. The frontend relies on the route guard
//   (`meta.roles: ['company']`) to keep non-company roles off these
//   views; the wrappers themselves do not branch on auth state.
//
// PAGINATION / FILTERS.
//   Neither endpoint takes query params -- both are single-shot
//   aggregates scoped to the authenticated company. No
//   `buildQueryString` ceremony required.
//
// SCOPE NOTE (F5.1 B0).
//   This file ships only the two wrappers. Pinia stores
//   (`companyProfile`, `companyDashboard`) land in B1; the wrappers
//   stay stateless so both the dashboard view (F5.1) and any future
//   one-shot probe (e.g. settings preview) can reuse them without
//   pulling in store state.
// =============================================================================

import { api } from '@/api/client'
import type {
  CompanyAnalyticsResponse,
  CompanyDashboardResponse,
} from '@/api/types'

/**
 * GET /api/v1/company/dashboard
 *
 * Single-payload dashboard aggregate for the authenticated company:
 *   - passive_balance        ledger snapshot (confirmed + frozen)
 *   - total_revenue_cents    lifetime revenue
 *   - total_options_sold     sale + installment_tranche units
 *                            (Sprint 4.6 hotfix)
 *   - products_count         number of products owned by the company
 *   - pool                   active OptionPool snapshot, or `null`
 *                            when staff has not created a pool yet
 *   - recent_transactions    last 20 transactions, newest first
 *
 * The recent_transactions block is embedded in this response on
 * purpose -- callers must NOT issue a second `/transactions` fetch.
 */
export function getCompanyDashboard(): Promise<CompanyDashboardResponse> {
  return api.get<CompanyDashboardResponse>('/api/v1/company/dashboard')
}

/**
 * GET /api/v1/company/analytics
 *
 * Analytics aggregate for the authenticated company:
 *   - sales_by_month     time-series for the dashboard chart
 *   - sales_by_product   per-product breakdown for the table view
 *   - top-line totals    revenue / options-sold mirrors of the
 *                        dashboard endpoint (so the analytics view
 *                        can render without a second fetch)
 *
 * Same auth contract as /company/dashboard: 403 without a
 * `CompanyProfile`.
 */
export function getCompanyAnalytics(): Promise<CompanyAnalyticsResponse> {
  return api.get<CompanyAnalyticsResponse>('/api/v1/company/analytics')
}
