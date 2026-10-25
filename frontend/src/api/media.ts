// =============================================================================
// AIVIS.ONE Frontend -- Project pictures API (H36 P-131)
// =============================================================================
//
// A project's logo, its logo for the dark theme, its cover, and a product's
// cover are files in our storage. These wrappers upload and remove them:
//
//   PUT|DELETE /api/v1/staff/companies/{id}/media/{slot}                  (project_manage)
//   PUT|DELETE /api/v1/companies/me/media/{slot}                          (the project itself)
//   PUT|DELETE /api/v1/staff/companies/{id}/products/{productId}/cover    (project_manage)
//
// slot is `logo`, `logo-dark` or `cover`. A PUT answers with the updated
// project (CompanyResponse) or product (ProductResponse), its links signed
// afresh; a DELETE answers 204, or 404 when there was nothing to remove.
//
// Uploads are multipart, which the JSON `api` client cannot send (it sets
// Content-Type: application/json), so they go through fetch() here -- the
// same shape as uploadRoadmapCover in staff-companies.ts. The browser sets
// `multipart/form-data; boundary=...` itself; setting it by hand would drop
// the boundary.
//
// The server derives the type from the filename extension (png, jpg, jpeg,
// webp) and checks the size (MEDIA_LIMITS below mirrors it); the screens
// check both first to spare an obvious 400.
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
import type { CompanyResponse, ProductResponse } from '@/api/generated'

/** A picture of a project, as written in the URL. */
export type CompanyMediaSlot = 'logo' | 'logo-dark' | 'cover'

/** The types the server accepts (by extension; these are their mimes). */
export const MEDIA_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp'] as const

/** The `accept` of a file input for a picture. */
export const MEDIA_IMAGE_ACCEPT = MEDIA_IMAGE_TYPES.join(',')

const MiB = 1024 * 1024

/**
 * Size limits, mirroring backend companies/constants.py: COMPANY_LOGO_MAX_BYTES
 * (1 MiB, both logos -- their bytes go into every purchase agreement) and
 * ROADMAP_COVER_MAX_BYTES (10 MiB, the project's and a product's cover).
 */
export const MEDIA_LIMITS = {
  logo: 1 * MiB,
  'logo-dark': 1 * MiB,
  cover: 10 * MiB,
  productCover: 10 * MiB,
} as const

/** Why a picked file is refused before upload, or null when it may go. */
export function checkMediaImage(file: File, maxBytes: number): 'type' | 'size' | null {
  if (!(MEDIA_IMAGE_TYPES as readonly string[]).includes(file.type)) return 'type'
  if (file.size > maxBytes) return 'size'
  return null
}

// 30s upload window (vs the 15s JSON default), as for the roadmap cover.
const UPLOAD_TIMEOUT_MS = 30_000

/** PUT one file as the multipart field `file`; the JSON answer or a typed error. */
async function putImage<T>(path: string, file: File): Promise<T> {
  const form = new FormData()
  form.append('file', file)

  const headers: Record<string, string> = {}
  const token = getAuthToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS)
  try {
    let response: Response
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
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

    return data as T
  } finally {
    clearTimeout(timeoutId)
  }
}

/** Staff: upload or replace a project's picture. */
export function uploadStaffCompanyMedia(
  companyId: string,
  slot: CompanyMediaSlot,
  file: File,
): Promise<CompanyResponse> {
  return putImage(`/api/v1/staff/companies/${companyId}/media/${slot}`, file)
}

/** Staff: remove a project's picture. 404 when there is none. */
export function deleteStaffCompanyMedia(companyId: string, slot: CompanyMediaSlot): Promise<void> {
  return api.delete(`/api/v1/staff/companies/${companyId}/media/${slot}`)
}

/** The project itself: upload or replace one of its pictures. */
export function uploadOwnCompanyMedia(
  slot: CompanyMediaSlot,
  file: File,
): Promise<CompanyResponse> {
  return putImage(`/api/v1/companies/me/media/${slot}`, file)
}

/** The project itself: remove one of its pictures. 404 when there is none. */
export function deleteOwnCompanyMedia(slot: CompanyMediaSlot): Promise<void> {
  return api.delete(`/api/v1/companies/me/media/${slot}`)
}

/** Staff: upload or replace a product's cover. */
export function uploadStaffProductCover(
  companyId: string,
  productId: string,
  file: File,
): Promise<ProductResponse> {
  return putImage(`/api/v1/staff/companies/${companyId}/products/${productId}/cover`, file)
}

/** Staff: remove a product's cover. 404 when there is none. */
export function deleteStaffProductCover(companyId: string, productId: string): Promise<void> {
  return api.delete(`/api/v1/staff/companies/${companyId}/products/${productId}/cover`)
}
