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
//   GET /api/v1/staff/companies/{id}                -- detail (+ roadmap)
//   GET   /api/v1/staff/companies/{id}/price-history -- price history (B3)
//   PATCH /api/v1/staff/companies/{id}/price         -- change price (C2)
//   GET   /api/v1/staff/companies/{id}/templates     -- template list (C2)
//   GET   /api/v1/staff/companies/{id}/templates/{tid} -- template detail (C2)
//   GET    /api/v1/staff/companies/{id}/attachments         -- doc list (C2)
//   PATCH  /api/v1/staff/companies/{id}/attachments/reorder -- reorder (C2)
//   DELETE /api/v1/staff/companies/{id}/attachments/{aid}   -- soft-delete (C2)
//
// Endpoints deferred to Block C / D:
//   POST   /api/v1/staff/companies
//   PATCH  /api/v1/staff/companies/{id}
//   POST   /api/v1/staff/companies/{id}/roadmap
//   PATCH  /api/v1/staff/companies/{id}/roadmap/{item_id}
//   DELETE /api/v1/staff/companies/{id}/roadmap/{item_id}
//   PATCH  /api/v1/staff/companies/{id}/roadmap/reorder
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  CompanyDetailResponse,
  CompanyListResponse,
  CompanyResponse,
  PriceHistoryListResponse,
  ReorderAttachmentsRequest,
  StaffAttachmentResponse,
  TemplateDetailResponse,
  TemplateResponse,
  UpdatePriceRequest,
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
 * GET /api/v1/staff/companies/{id} -- one company's full detail in ANY
 * status (active / hidden / archived) plus its inline roadmap.
 *
 * iter 2.7 Block C enabler. Unlike api/companies.ts::getCompany (the
 * public detail, which 404s on non-active companies and omits
 * distribution_config), this staff variant returns the full
 * CompanyResponse projection regardless of status -- so
 * StaffCompanyDetailView can open a hidden / archived company.
 *
 * 404 only when the company id does not exist at all.
 */
export function fetchStaffCompany(
  companyId: string,
): Promise<CompanyDetailResponse> {
  return api.get<CompanyDetailResponse>(
    `/api/v1/staff/companies/${companyId}`,
  )
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


/**
 * PATCH /api/v1/staff/companies/{id}/price -- change the company's
 * share price (iter 2.7 C2). Cascades to active/hidden products
 * server-side and appends a CompanyPriceHistory row.
 *
 * Requires company_manage AND financial_operations server-side; the
 * Price section gates the edit CTA on both (FP-23). Returns the
 * updated CompanyResponse (new price reflected).
 */
export function updateStaffCompanyPrice(
  companyId: string,
  body: UpdatePriceRequest,
): Promise<CompanyResponse> {
  return api.patch<CompanyResponse>(
    `/api/v1/staff/companies/${companyId}/price`,
    body,
  )
}


/**
 * GET /api/v1/staff/companies/{id}/templates -- staff template list
 * (iter 2.7 C2). Returns per-company rows merged with platform-default
 * `active` fallbacks for any (kind, language) the company has not
 * overridden, so staff sees what the renderer would actually pick.
 * Each row carries is_platform_default (computed) to tell overrides
 * from fallbacks.
 *
 * NOT paginated -- the backend returns a plain array (templates per
 * company are few). Filters (all optional, backend StrEnum, 422 on a
 * bad value):
 *   - kind:     purchase_agreement | gift_certificate |
 *               installment_subcontract | ownership_certificate
 *   - language: en | ru | de | ar
 *   - status:   draft | active | archived (per-company branch only)
 *
 * 404 when the company id does not exist.
 */
export function fetchStaffCompanyTemplates(
  companyId: string,
  params?: {
    kind?: string
    language?: string
    status?: string
  },
): Promise<TemplateResponse[]> {
  const qs = buildQueryString({
    kind: params?.kind,
    language: params?.language,
    status: params?.status,
  })
  return api.get<TemplateResponse[]>(
    `/api/v1/staff/companies/${companyId}/templates${qs}`,
  )
}

/**
 * GET /api/v1/staff/companies/{id}/templates/{templateId} -- one
 * template with the HTML body inlined for inspection (iter 2.7 C2).
 * Adds html_content + storage_prefix on top of the list shape.
 *
 * Platform-default rows (company_id IS NULL) are reachable here too.
 * 404 on an unknown company or template id; a 500 surfaces a broken
 * template (MinIO object missing / storage down) -- the caller shows
 * a load error rather than treating it as "no template".
 */
export function fetchStaffCompanyTemplate(
  companyId: string,
  templateId: string,
): Promise<TemplateDetailResponse> {
  return api.get<TemplateDetailResponse>(
    `/api/v1/staff/companies/${companyId}/templates/${templateId}`,
  )
}


/**
 * GET /api/v1/staff/companies/{id}/attachments -- staff document list
 * (iter 2.7 C2). Returns every non-deleted attachment (all publish
 * states) unless include_deleted is set. NOT paginated -- the backend
 * returns a plain array.
 *
 * Filters (all optional):
 *   - category:        exact category match
 *   - category_prefix: prefix match (e.g. "legal/" for a subtree)
 *   - language:        en | ru | de | ar
 *   - include_deleted: true to surface soft-deleted rows (trash view)
 *
 * 404 when the company id does not exist.
 */
export function fetchStaffCompanyAttachments(
  companyId: string,
  params?: {
    category?: string
    category_prefix?: string
    language?: string
    include_deleted?: boolean
  },
): Promise<StaffAttachmentResponse[]> {
  const qs = buildQueryString({
    category: params?.category,
    category_prefix: params?.category_prefix,
    language: params?.language,
    include_deleted: params?.include_deleted,
  })
  return api.get<StaffAttachmentResponse[]>(
    `/api/v1/staff/companies/${companyId}/attachments${qs}`,
  )
}

/**
 * PATCH /api/v1/staff/companies/{id}/attachments/reorder -- bulk
 * reorder within ONE (company, category) scope (iter 2.7 C2).
 *
 * `item_ids` must be the COMPLETE ordered list of every non-deleted
 * attachment in that category. A partial / extended / duplicate list
 * is rejected 400 with the `attachments_reorder_set_mismatch:` prefix
 * -- the caller catches that prefix and tells the user the list is
 * stale (someone else changed it), then reloads. Returns 204.
 */
export function reorderStaffCompanyAttachments(
  companyId: string,
  body: ReorderAttachmentsRequest,
): Promise<void> {
  return api.patch<void>(
    `/api/v1/staff/companies/${companyId}/attachments/reorder`,
    body,
  )
}

/**
 * DELETE /api/v1/staff/companies/{id}/attachments/{attachmentId} --
 * soft-delete one attachment (iter 2.7 C2). Sets is_deleted=True; the
 * MinIO object is left in place (hard delete is a separate admin-only
 * endpoint not surfaced here). Returns 204.
 */
export function deleteStaffCompanyAttachment(
  companyId: string,
  attachmentId: string,
): Promise<void> {
  return api.delete(
    `/api/v1/staff/companies/${companyId}/attachments/${attachmentId}`,
  )
}
