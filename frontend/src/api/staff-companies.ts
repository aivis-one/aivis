// =============================================================================
// AIVIS.ONE Frontend -- Staff Companies API (iter 2.7 Block B)
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
//   POST   /api/v1/staff/companies/{id}/roadmap             -- create item (D1)
//   PATCH  /api/v1/staff/companies/{id}/roadmap/reorder     -- reorder (D1)
//   PATCH  /api/v1/staff/companies/{id}/roadmap/{item_id}   -- update item (D1)
//   DELETE /api/v1/staff/companies/{id}/roadmap/{item_id}   -- soft-delete (D1)
//
// Endpoints deferred to Block C / D:
//   POST   /api/v1/staff/companies
//   PATCH  /api/v1/staff/companies/{id}
//
// Block D2 (cover upload) adds two more here -- they speak multipart
// via fetch() (the JSON `api` client cannot send FormData), so they
// land alongside the D2 view that drives them:
//   PUT    /api/v1/staff/companies/{id}/roadmap/{item_id}/cover
//   DELETE /api/v1/staff/companies/{id}/roadmap/{item_id}/cover
// =============================================================================
import {
  API_BASE_URL,
  ApiNetworkError,
  ApiResponseError,
  ApiTimeoutError,
  api,
  getAuthToken,
  parseRetryAfterHeader,
} from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  CompanyDetailResponse,
  CompanyListResponse,
  CompanyResponse,
  CreateRoadmapItemRequest,
  PriceHistoryListResponse,
  ReorderAttachmentsRequest,
  ReorderRoadmapRequest,
  RoadmapItemResponse,
  StaffAttachmentResponse,
  TemplateDetailResponse,
  TemplateResponse,
  UpdatePriceRequest,
  UpdateRoadmapItemRequest,
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
    kind?:
      | 'purchase_agreement'
      | 'gift_certificate'
      | 'installment_subcontract'
      | 'ownership_certificate'
    language?: 'en' | 'ru' | 'de' | 'ar'
    status?: 'draft' | 'active' | 'archived'
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


// ---------------------------------------------------------------------------
// Roadmap CRUD + reorder (iter 2.7 D1, R1 §5)
// ---------------------------------------------------------------------------
//
// The roadmap itself is NOT fetched here -- it arrives inline on
// CompanyDetailResponse.roadmap via fetchStaffCompany, which the parent
// StaffCompanyDetailView already loads and provides through
// STAFF_COMPANY_KEY. The section mutates via these endpoints and then
// calls ctx.reload() to re-pull the detail (cheap, unpaginated).
//
// Per-kind invariants (milestone / event / announcement) and the
// milestone state machine (completed is terminal) are enforced
// server-side; the section pre-validates in the form to avoid an
// obvious 400, but the backend is the source of truth.

/**
 * POST /api/v1/staff/companies/{id}/roadmap -- create one roadmap item
 * (R1 §5). Requires company_manage server-side.
 *
 * `kind` is required and immutable after create. Per-kind body rules
 * (Pydantic _check_kind_rules): milestone forbids valid_until; event
 * requires target_date + valid_until with valid_until > target_date;
 * announcement forbids target_date / valid_until / status. A violation
 * is a 422 (Pydantic) -- the form mirrors these rules to prevent it.
 *
 * `cover_storage_key` is NOT part of the body -- the cover is managed
 * by the dedicated D2 multipart endpoint. Returns the created item
 * (201) including a presigned `cover_url` (null on create).
 */
export function createRoadmapItem(
  companyId: string,
  body: CreateRoadmapItemRequest,
): Promise<RoadmapItemResponse> {
  return api.post<RoadmapItemResponse>(
    `/api/v1/staff/companies/${companyId}/roadmap`,
    body,
  )
}

/**
 * PATCH /api/v1/staff/companies/{id}/roadmap/{itemId} -- partial update
 * of a roadmap item (R1 §5). Requires company_manage server-side.
 *
 * `kind` is intentionally absent from UpdateRoadmapItemRequest -- it is
 * immutable. Send ONLY the fields that actually changed: the backend
 * uses exclude_unset + a `...` sentinel to tell "field omitted" (keep)
 * from "field set to null" (clear). Sending an unchanged field as null
 * would wipe it.
 *
 * Milestone state machine: moving a `completed` milestone to any other
 * status is a 400 ("Cannot move a completed milestone to another
 * status. ..."). The text carries no machine-readable prefix, so the
 * section blocks this in the form (disabled status select on a
 * completed milestone) rather than parsing the message.
 */
export function updateRoadmapItem(
  companyId: string,
  itemId: string,
  body: UpdateRoadmapItemRequest,
): Promise<RoadmapItemResponse> {
  return api.patch<RoadmapItemResponse>(
    `/api/v1/staff/companies/${companyId}/roadmap/${itemId}`,
    body,
  )
}

/**
 * DELETE /api/v1/staff/companies/{id}/roadmap/{itemId} -- soft-delete
 * one roadmap item (R1 §5). Sets is_deleted=True server-side; any
 * uploaded cover object is left in MinIO. Returns 204. Requires
 * company_manage server-side.
 */
export function deleteRoadmapItem(
  companyId: string,
  itemId: string,
): Promise<void> {
  return api.delete(
    `/api/v1/staff/companies/${companyId}/roadmap/${itemId}`,
  )
}

/**
 * PATCH /api/v1/staff/companies/{id}/roadmap/reorder -- bulk reorder
 * (R1 §5). Requires company_manage server-side.
 *
 * `item_ids` must be the COMPLETE ordered list of every non-deleted
 * roadmap item for the company (per-company scope, NOT per-kind). A
 * partial / extended / duplicate list is rejected 400.
 *
 * NOTE: unlike the attachments reorder (which emits the
 * `attachments_reorder_set_mismatch:` prefix), the roadmap reorder
 * error message is plain prose ("Reorder mismatch: ...", "Duplicate
 * IDs in reorder list") with NO machine-readable prefix. The section
 * therefore treats any ApiResponseError from this call as a stale-list
 * signal: it shows a generic error toast and reloads, rather than
 * matching on a prefix. Returns the items in their new order.
 */
export function reorderRoadmap(
  companyId: string,
  body: ReorderRoadmapRequest,
): Promise<RoadmapItemResponse[]> {
  return api.patch<RoadmapItemResponse[]>(
    `/api/v1/staff/companies/${companyId}/roadmap/reorder`,
    body,
  )
}


// ---------------------------------------------------------------------------
// Roadmap cover image (iter 2.7 D2, R1 §5.5)
// ---------------------------------------------------------------------------
//
// Covers are multipart uploads, which the JSON `api` client cannot
// send -- it hard-codes Content-Type: application/json. These two go
// through a raw fetch() instead (the same shape as attachments.ts's
// _downloadBlob, minus the blob materialisation -- the cover endpoint
// returns JSON, not a redirect to bytes).

// 30s upload window (vs the 15s JSON default) -- a 10 MiB image over
// slow mobile needs the slack, mirroring the attachments download
// timeout.
const COVER_UPLOAD_TIMEOUT_MS = 30_000

/**
 * PUT /api/v1/staff/companies/{id}/roadmap/{itemId}/cover -- upload or
 * replace a roadmap item's cover image (R1 §5.5). Requires
 * company_manage server-side.
 *
 * Multipart with a single form field named `file` (matches the
 * backend `file: UploadFile = File(...)` parameter). The mime is
 * derived server-side from the filename extension -- the multipart
 * Content-Type the browser sets is ignored there to neutralise
 * spoofed-mime stored-XSS, so we do NOT set it ourselves either:
 * letting the browser fill in `multipart/form-data; boundary=...` is
 * mandatory (a manual Content-Type would omit the boundary and the
 * upload would fail to parse).
 *
 * Whitelist (PNG / JPEG / WEBP) and the 10 MiB cap are enforced
 * server-side; the section pre-checks both before calling to avoid an
 * obvious 400. Returns the updated RoadmapItemResponse with a fresh
 * presigned `cover_url`.
 *
 * Errors mirror the JSON client surface: ApiResponseError (4xx/5xx,
 * with retryAfter on 429), ApiTimeoutError (abort), ApiNetworkError
 * (transport). The caller renders the toast.
 */
export async function uploadRoadmapCover(
  companyId: string,
  itemId: string,
  file: File,
): Promise<RoadmapItemResponse> {
  const url =
    `${API_BASE_URL}/api/v1/staff/companies/${companyId}`
    + `/roadmap/${itemId}/cover`

  const form = new FormData()
  // Field name MUST be `file` to bind the backend UploadFile param.
  form.append('file', file)

  // NB: no Content-Type header -- the browser sets multipart/form-data
  // with the boundary. Only the auth header is added by hand.
  const headers: Record<string, string> = {}
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(
    () => controller.abort(),
    COVER_UPLOAD_TIMEOUT_MS,
  )

  try {
    let response: Response
    try {
      response = await fetch(url, {
        method: 'PUT',
        headers,
        body: form,
        signal: controller.signal,
      })
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiTimeoutError()
      }
      throw new ApiNetworkError(
        err instanceof Error ? err.message : 'Network error',
      )
    }

    // Parse the JSON body. On success it's the RoadmapItemResponse; on
    // error it's the FastAPI detail / AivisError message envelope.
    let data: unknown
    try {
      data = await response.json()
    } catch {
      const retryAfter =
        response.status === 429 ? parseRetryAfterHeader(response) : undefined
      throw new ApiResponseError(
        response.status,
        `HTTP ${response.status}: non-JSON response`,
        retryAfter,
      )
    }

    if (!response.ok) {
      // Mirror client.ts extractErrorMessage: prefer `detail`, then
      // `message`, else a status string.
      let detail = `HTTP ${response.status}`
      if (data && typeof data === 'object') {
        const obj = data as { detail?: unknown; message?: unknown }
        if ('detail' in obj && obj.detail != null) {
          detail = String(obj.detail)
        } else if ('message' in obj && typeof obj.message === 'string') {
          detail = obj.message
        }
      }
      const retryAfter =
        response.status === 429 ? parseRetryAfterHeader(response) : undefined
      throw new ApiResponseError(response.status, detail, retryAfter)
    }

    return data as RoadmapItemResponse
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * DELETE /api/v1/staff/companies/{id}/roadmap/{itemId}/cover -- remove
 * the cover image (R1 §5.5). Requires company_manage server-side.
 *
 * Plain JSON-client DELETE (no multipart), returns 204. The backend
 * 404s when the item has no cover -- an explicit "nothing to remove"
 * rather than a silent success -- so the caller treats a 404 here as a
 * benign already-removed case if it wants. Nulls cover_storage_key;
 * the section reloads the detail to drop the thumbnail.
 */
export function deleteRoadmapCover(
  companyId: string,
  itemId: string,
): Promise<void> {
  return api.delete(
    `/api/v1/staff/companies/${companyId}/roadmap/${itemId}/cover`,
  )
}
