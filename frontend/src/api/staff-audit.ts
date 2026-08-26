// =============================================================================
// AIVIS.ONE Frontend -- Staff Company Audit API (TASK-30 batch 1 W3)
// =============================================================================
//
// Typed wrapper for /api/v1/staff/audit/* (backend
// app/modules/audit/router.py). Distinct from api/staff-companies.ts,
// which speaks the company CRUD/read surfaces -- this module covers the
// admin audit-feed read surface only: a plain paginated, date-filterable
// history of writes a project (company) made to itself, recorded via
// record_audit(target_type="company"). Read-only, no mutation
// affordances -- see the backend router's module docstring for the
// TASK-30 ruling that keeps this a plain log viewer (no approve /
// reject / acknowledge, none of that exists server-side).
//
// Endpoints covered here:
//   GET /api/v1/staff/audit/companies -- paginated, newest-first feed
// =============================================================================
import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type { CompanyAuditFeedResponse } from '@/api/types'

/**
 * GET /api/v1/staff/audit/companies -- paginated, newest-first feed of
 * company (project) writes.
 *
 * Filters (all optional, combinable):
 *   - company_id: scope to one project's full write history (UUID).
 *     StaffCompanyAuditSection always passes the current route's
 *     company id.
 *   - date_from / date_to: inclusive ISO datetime bounds on created_at.
 *
 * Requires project_manage server-side
 * (require_staff_permission("project_manage")).
 *
 * Pagination: page (1-indexed), per_page (1..100), same envelope shape
 * as the other staff list endpoints.
 */
export function fetchCompanyAuditFeed(params?: {
  company_id?: string
  date_from?: string
  date_to?: string
  page?: number
  per_page?: number
}): Promise<CompanyAuditFeedResponse> {
  const qs = buildQueryString({
    company_id: params?.company_id,
    date_from: params?.date_from,
    date_to: params?.date_to,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<CompanyAuditFeedResponse>(`/api/v1/staff/audit/companies${qs}`)
}
