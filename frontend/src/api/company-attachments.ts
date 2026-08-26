// =============================================================================
// AIVIS.ONE Frontend -- Company Attachments Self-Service API (TASK-30)
// =============================================================================
//
// Typed wrappers for /api/v1/company/attachments/* (backend
// companies/attachments_company_router.py). Distinct from
// api/staff-companies.ts's attachment functions, which speak the STAFF
// surface (/api/v1/staff/companies/{id}/attachments/*) and take an
// explicit companyId, and from api/attachments.ts (if it exists) which
// speaks the read-only auth-flow investor surface
// (/api/v1/companies/{id}/attachments). Every function here operates on
// the CALLER'S OWN company -- there is no companyId parameter anywhere
// in this module because there is no {company_id} in any of these URLs;
// the backend resolves it server-side from the auth token via
// get_current_company_profile.
//
// Reuses the SAME generated AttachmentPatchBody / ReorderAttachmentsRequest
// / AttachmentResponse types api/staff-companies.ts uses for the sibling
// staff surface (companies/schemas.py) -- there is nothing company-specific
// to add on the wire-shape side for those three. The ONE type that has no
// generated counterpart is the multipart `metadata` field on create: the
// backend parses it via AttachmentInboxMetadata.model_validate_json(), but
// that schema is never used as a direct FastAPI request/response model
// anywhere in the OpenAPI surface (it only ever appears inside a Form
// string), so generate_ts_types.py never emits it. AttachmentUploadMetadata
// below is a hand-written mirror of AttachmentInboxMetadata's fields --
// keep the two in sync if the backend schema changes.
//
// Endpoints covered here:
//   GET    /api/v1/company/attachments                    -- list own attachments
//   POST   /api/v1/company/attachments                     -- upload one
//   PATCH  /api/v1/company/attachments/{attachmentId}       -- update metadata
//   PATCH  /api/v1/company/attachments/{attachmentId}/replace -- replace file
//   DELETE /api/v1/company/attachments/{attachmentId}       -- soft-delete
//   PATCH  /api/v1/company/attachments/reorder               -- reorder
//
// NO hard-delete wrapper here -- the backend router has no
// `DELETE .../{attachmentId}/hard` route at all on this surface (TASK-30
// ruling: project gets soft-delete only; see attachments_company_router.py's
// module docstring for the full reasoning).
//
// Upload / replace mirror uploadRoadmapCover / uploadOwnRoadmapCover in
// api/staff-companies.ts / api/company-roadmap.ts byte for byte (multipart
// via raw fetch(), the JSON `api` client cannot send FormData) -- see
// those functions' docstrings for the full error-handling rationale; not
// repeated here. The one difference: create() sends TWO form fields
// (`metadata` JSON string + `file` binary) instead of one, matching the
// backend's `metadata: str = Form(...)` + `file: UploadFile = File(...)`
// signature.
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
  AttachmentPatchBody,
  AttachmentResponse,
  ReorderAttachmentsRequest,
} from '@/api/types'

/**
 * Hand-written mirror of the backend's AttachmentInboxMetadata
 * (companies/schemas.py) -- see this module's header comment for why it
 * cannot be re-exported from generated.ts. Keep in sync with the backend
 * schema: `title` is the only required field; everything else has a
 * safety-first default there (category="unsorted", language="en",
 * order=0, is_published=false, is_public=false) -- send only what the
 * form actually collected and let the backend fill in the rest.
 */
export interface AttachmentUploadMetadata {
  title: string
  description?: string | null
  category?: string
  language?: string
  order?: number
  is_published?: boolean
  is_public?: boolean
}

/**
 * GET /api/v1/company/attachments -- the caller's own non-deleted
 * attachments. Requires role=company server-side (403 for any other
 * role). Unlike the staff list, there is no `include_deleted` filter --
 * a project has no restore capability on this surface.
 *
 * Filters (all optional, combinable): category (exact match),
 * category_prefix (LIKE prefix%), language (exact ISO 639-1 code).
 */
export function fetchOwnAttachments(params?: {
  category?: string
  category_prefix?: string
  language?: string
}): Promise<AttachmentResponse[]> {
  const qs = buildQueryString({
    category: params?.category,
    category_prefix: params?.category_prefix,
    language: params?.language,
  })
  return api.get<AttachmentResponse[]>(`/api/v1/company/attachments${qs}`)
}

/**
 * PATCH /api/v1/company/attachments/{attachmentId} -- partial update of
 * an own attachment's metadata. Send ONLY the fields that actually
 * changed -- exclude_unset semantics, same as the staff surface: an
 * omitted field is kept, an explicit null clears `description`.
 *
 * 404 (never 403) when attachmentId belongs to a different company.
 */
export function updateOwnAttachment(
  attachmentId: string,
  body: AttachmentPatchBody,
): Promise<AttachmentResponse> {
  return api.patch<AttachmentResponse>(`/api/v1/company/attachments/${attachmentId}`, body)
}

/**
 * DELETE /api/v1/company/attachments/{attachmentId} -- soft-delete an
 * own attachment. Sets is_deleted=True server-side; the MinIO object is
 * left in place (no hard-delete on this surface at all). Returns 204.
 * 404 (never 403) on cross-company attachmentId.
 */
export function deleteOwnAttachment(attachmentId: string): Promise<void> {
  return api.delete(`/api/v1/company/attachments/${attachmentId}`)
}

/**
 * PATCH /api/v1/company/attachments/reorder -- bulk reorder of the
 * caller's OWN attachments inside one category.
 *
 * `item_ids` must be the COMPLETE ordered list of every non-deleted
 * attachment in (own company_id, body.category). A partial / extended /
 * duplicate list -- or any id belonging to a different company -- is
 * rejected 400 with an `attachments_reorder_set_mismatch:` prefix, same
 * as the staff surface: the view should treat that prefix as a
 * stale-list signal and reload. Returns 204 (no body) -- unlike the
 * roadmap self-service reorder, this endpoint matches its direct staff
 * sibling's shape rather than returning the reordered list.
 */
export function reorderOwnAttachments(body: ReorderAttachmentsRequest): Promise<void> {
  return api.patch<void>('/api/v1/company/attachments/reorder', body)
}

// ---------------------------------------------------------------------------
// Upload / replace -- multipart via raw fetch()
// ---------------------------------------------------------------------------

// 60s upload window -- attachments allow documents up to 100MB
// (Nginx client_max_body_size, backend R2 Q-ATT-3), much larger than the
// 10MiB roadmap cover cap that COVER_UPLOAD_TIMEOUT_MS (30s) was sized
// for. Slow mobile uploading a large PDF needs the extra slack.
const ATTACHMENT_UPLOAD_TIMEOUT_MS = 60_000

/** Shared response-parsing / error-mapping tail for both multipart calls
 * below. Mirrors uploadOwnRoadmapCover's error handling exactly -- see
 * that function's docstring in api/company-roadmap.ts for the full
 * rationale (ApiTimeoutError on abort, ApiNetworkError on transport
 * failure, ApiResponseError with `detail`/`message` extraction and
 * Retry-After on 4xx/5xx).
 */
async function _sendAttachmentMultipart(
  url: string,
  method: 'POST' | 'PATCH',
  form: FormData,
): Promise<AttachmentResponse> {
  const headers: Record<string, string> = {}
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), ATTACHMENT_UPLOAD_TIMEOUT_MS)

  try {
    let response: Response
    try {
      response = await fetch(url, {
        method,
        headers,
        body: form,
        signal: controller.signal,
      })
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiTimeoutError()
      }
      throw new ApiNetworkError(err instanceof Error ? err.message : 'Network error')
    }

    let data: unknown
    try {
      data = await response.json()
    } catch {
      const retryAfter = response.status === 429 ? parseRetryAfterHeader(response) : undefined
      throw new ApiResponseError(
        response.status,
        `HTTP ${response.status}: non-JSON response`,
        retryAfter,
      )
    }

    if (!response.ok) {
      let detail = `HTTP ${response.status}`
      if (data && typeof data === 'object') {
        const obj = data as { detail?: unknown; message?: unknown }
        if ('detail' in obj && obj.detail != null) {
          detail = String(obj.detail)
        } else if ('message' in obj && typeof obj.message === 'string') {
          detail = obj.message
        }
      }
      const retryAfter = response.status === 429 ? parseRetryAfterHeader(response) : undefined
      throw new ApiResponseError(response.status, detail, retryAfter)
    }

    return data as AttachmentResponse
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * POST /api/v1/company/attachments -- upload a new attachment on the
 * caller's own company.
 *
 * Multipart with two form fields: `metadata` (a JSON-stringified
 * AttachmentUploadMetadata) and `file` (the binary), matching the
 * backend's `metadata: str = Form(...)` + `file: UploadFile = File(...)`
 * signature exactly -- FastAPI cannot mix a Form field and a JSON body
 * in one route, so metadata travels as a string field, not the request
 * body. No Content-Type is set by hand -- the browser fills in
 * `multipart/form-data; boundary=...`; the mime itself is derived
 * server-side from the filename extension via
 * validate_attachment_mime_by_filename, ignoring whatever Content-Type
 * the browser reports (spoofed-mime stored-XSS defence -- same as the
 * roadmap cover endpoints).
 *
 * The whitelist (PDF / PPTX / DOCX / XLSX / PNG / JPEG / WEBP) and the
 * 100MB cap are enforced server-side (constants.py
 * ALLOWED_ATTACHMENT_MIME_TYPES, Nginx client_max_body_size); the view
 * should pre-check the mime whitelist client-side to avoid an obvious
 * 400, but the 100MB cap is Nginx's job, not app code's -- there is no
 * client-side size check to mirror (unlike the 10MiB roadmap cover cap,
 * which the app enforces itself before Nginx would ever see the
 * request).
 */
export async function createOwnAttachment(
  metadata: AttachmentUploadMetadata,
  file: File,
): Promise<AttachmentResponse> {
  const url = `${API_BASE_URL}/api/v1/company/attachments`

  const form = new FormData()
  form.append('metadata', JSON.stringify(metadata))
  form.append('file', file)

  return _sendAttachmentMultipart(url, 'POST', form)
}

/**
 * PATCH /api/v1/company/attachments/{attachmentId}/replace -- swap the
 * binary content of an own attachment. Metadata (title / category /
 * publish flags / ...) is left untouched -- use updateOwnAttachment for
 * that. Single form field `file`, same mime/size handling as create().
 * 404 (never 403) on cross-company attachmentId.
 */
export async function replaceOwnAttachmentFile(
  attachmentId: string,
  file: File,
): Promise<AttachmentResponse> {
  const url = `${API_BASE_URL}/api/v1/company/attachments/${attachmentId}/replace`

  const form = new FormData()
  form.append('file', file)

  return _sendAttachmentMultipart(url, 'PATCH', form)
}
