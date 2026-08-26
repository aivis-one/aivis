// =============================================================================
// AIVIS.ONE Frontend -- Company Roadmap Self-Service API (TASK-30)
// =============================================================================
//
// Typed wrappers for /api/v1/company/roadmap/* (backend
// companies/roadmap_company_router.py). Distinct from
// api/staff-companies.ts's roadmap functions, which speak the STAFF
// surface (/api/v1/staff/companies/{id}/roadmap/*) and take an explicit
// companyId. Every function here operates on the CALLER'S OWN company --
// there is no companyId parameter anywhere in this module because there
// is no {company_id} in any of these URLs; the backend resolves it
// server-side from the auth token via get_current_company_profile.
//
// Reuses the SAME generated request/response types as api/staff-companies.ts
// (CreateRoadmapItemRequest, UpdateRoadmapItemRequest, ReorderRoadmapRequest,
// RoadmapItemResponse) -- the backend reuses the identical Pydantic
// schemas for both surfaces (companies/schemas.py), so there is nothing
// company-specific to add on the wire-shape side.
//
// Endpoints covered here:
//   GET    /api/v1/company/roadmap                -- list own items
//   POST   /api/v1/company/roadmap                -- create item
//   PATCH  /api/v1/company/roadmap/{itemId}        -- update item
//   DELETE /api/v1/company/roadmap/{itemId}        -- soft-delete item
//   PATCH  /api/v1/company/roadmap/reorder         -- reorder items
//   PUT    /api/v1/company/roadmap/{itemId}/cover  -- upload/replace cover
//   DELETE /api/v1/company/roadmap/{itemId}/cover  -- remove cover
//
// Cover upload mirrors uploadRoadmapCover in api/staff-companies.ts byte
// for byte (multipart via raw fetch(), the JSON `api` client cannot send
// FormData) -- see that function's docstring for the full error-handling
// rationale; not repeated here.
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
import type {
  CreateRoadmapItemRequest,
  ReorderRoadmapRequest,
  RoadmapItemResponse,
  UpdateRoadmapItemRequest,
} from '@/api/types'

/**
 * GET /api/v1/company/roadmap -- the caller's own non-deleted roadmap
 * items, in display order. Requires role=company server-side (403 for
 * any other role).
 */
export function fetchOwnRoadmap(): Promise<RoadmapItemResponse[]> {
  return api.get<RoadmapItemResponse[]>('/api/v1/company/roadmap')
}

/**
 * POST /api/v1/company/roadmap -- create one roadmap item on the
 * caller's own company. Same per-kind body rules as the staff surface
 * (CreateRoadmapItemRequest._check_kind_rules, 422 on violation):
 * milestone forbids valid_until; event requires target_date +
 * valid_until with valid_until > target_date; announcement forbids
 * target_date / valid_until / status.
 *
 * `cover_storage_key` is NOT part of the body -- set via the dedicated
 * multipart cover endpoints below. Returns the created item (201).
 */
export function createOwnRoadmapItem(body: CreateRoadmapItemRequest): Promise<RoadmapItemResponse> {
  return api.post<RoadmapItemResponse>('/api/v1/company/roadmap', body)
}

/**
 * PATCH /api/v1/company/roadmap/{itemId} -- partial update of an own
 * roadmap item. `kind` is immutable (absent from
 * UpdateRoadmapItemRequest). Send ONLY the fields that actually
 * changed -- exclude_unset + `...` sentinel semantics, same as the
 * staff surface: an omitted field is kept, an explicit null clears it.
 *
 * 404 (never 403) when itemId belongs to a different company.
 *
 * Milestone state machine: moving a `completed` milestone to any other
 * status is a 400 with no machine-readable prefix -- the view blocks
 * this in the form rather than parsing the message.
 */
export function updateOwnRoadmapItem(
  itemId: string,
  body: UpdateRoadmapItemRequest,
): Promise<RoadmapItemResponse> {
  return api.patch<RoadmapItemResponse>(`/api/v1/company/roadmap/${itemId}`, body)
}

/**
 * DELETE /api/v1/company/roadmap/{itemId} -- soft-delete an own roadmap
 * item. Sets is_deleted=True server-side; any uploaded cover object is
 * left in MinIO. Returns 204. 404 (never 403) on cross-company itemId.
 */
export function deleteOwnRoadmapItem(itemId: string): Promise<void> {
  return api.delete(`/api/v1/company/roadmap/${itemId}`)
}

/**
 * PATCH /api/v1/company/roadmap/reorder -- bulk reorder of the caller's
 * OWN roadmap items.
 *
 * `item_ids` must be the COMPLETE ordered list of every non-deleted
 * roadmap item belonging to the caller's company. A partial / extended
 * / duplicate list -- or any id belonging to a different company -- is
 * rejected 400 (plain prose, no machine-readable prefix, same as the
 * staff surface): the view treats any ApiResponseError here as a
 * stale-list signal and reloads. Returns the items in their new order.
 */
export function reorderOwnRoadmap(body: ReorderRoadmapRequest): Promise<RoadmapItemResponse[]> {
  return api.patch<RoadmapItemResponse[]>('/api/v1/company/roadmap/reorder', body)
}

// 30s upload window (vs the 15s JSON default) -- a 10 MiB image over
// slow mobile needs the slack, mirroring api/staff-companies.ts's
// COVER_UPLOAD_TIMEOUT_MS.
const COVER_UPLOAD_TIMEOUT_MS = 30_000

/**
 * PUT /api/v1/company/roadmap/{itemId}/cover -- upload or replace an
 * own roadmap item's cover image.
 *
 * Multipart with a single form field named `file` (matches the backend
 * `file: UploadFile = File(...)` parameter). No Content-Type is set by
 * hand -- the browser fills in `multipart/form-data; boundary=...`,
 * which the backend requires to parse the body; the mime itself is
 * derived server-side from the filename extension, ignoring whatever
 * Content-Type the browser reports (spoofed-mime stored-XSS defence).
 *
 * Whitelist (PNG / JPEG / WEBP) and the 10 MiB cap are enforced
 * server-side; the view pre-checks both before calling, to avoid an
 * obvious 400. Returns the updated RoadmapItemResponse with a fresh
 * presigned `cover_url`.
 */
export async function uploadOwnRoadmapCover(
  itemId: string,
  file: File,
): Promise<RoadmapItemResponse> {
  const url = `${API_BASE_URL}/api/v1/company/roadmap/${itemId}/cover`

  const form = new FormData()
  form.append('file', file)

  const headers: Record<string, string> = {}
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), COVER_UPLOAD_TIMEOUT_MS)

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

    return data as RoadmapItemResponse
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * DELETE /api/v1/company/roadmap/{itemId}/cover -- remove the cover
 * image from an own roadmap item. Plain JSON-client DELETE, returns
 * 204. The backend 404s when the item has no cover -- an explicit
 * "nothing to remove" the caller can treat as a benign already-removed
 * case.
 */
export function deleteOwnRoadmapCover(itemId: string): Promise<void> {
  return api.delete(`/api/v1/company/roadmap/${itemId}/cover`)
}
