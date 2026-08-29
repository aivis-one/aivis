// =============================================================================
// AIVIS.ONE Frontend -- Company Self-Service Audit Feed API (TASK-39 item 7)
// =============================================================================
//
// Typed wrapper for GET /api/v1/company/audit (backend
// app/modules/audit/company_router.py). Distinct from api/staff-audit.ts,
// which speaks the STAFF feed (any company, admin-only, wider schema) --
// this module covers the company's own read of its own history only.
//
// NO company_id parameter exists here, on purpose: the backend forces
// company_id server-side from the caller's own CompanyProfile (via
// get_current_company_profile) -- there is nothing for a client to pass
// to select a different project, unlike fetchCompanyAuditFeed above.
//
// Response shape (CompanySelfAuditFeedResponse) is DELIBERATELY
// NARROWER than the staff feed's CompanyAuditEntryResponse: no
// actor_id / performed_by / on_behalf_of (a company never learns WHICH
// staff member wrote a row), no raw `data` (would leak values, e.g.
// price history) -- only id / event / created_at / actor_type /
// changed_fields (field NAMES only). See backend/app/modules/audit/
// schemas.py for the full reasoning.
// =============================================================================
import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type { CompanySelfAuditFeedResponse } from '@/api/types'

/**
 * GET /api/v1/company/audit -- paginated, newest-first feed of the
 * caller's OWN company (project) write history.
 *
 * Pagination: page (1-indexed), per_page (1..100), same envelope shape
 * as listMyPlans / the staff audit feed.
 */
export function fetchOwnAuditFeed(params?: {
  page?: number
  per_page?: number
}): Promise<CompanySelfAuditFeedResponse> {
  const qs = buildQueryString({
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<CompanySelfAuditFeedResponse>(`/api/v1/company/audit${qs}`)
}
