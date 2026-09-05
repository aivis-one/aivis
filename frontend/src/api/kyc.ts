// =============================================================================
// AIVIS.ONE Frontend -- KYC API client (H12)
// =============================================================================
//
// Four surfaces in one file because they are one feature:
//   submitKycApplication      -- the investor's multipart submission
//   fetchKycDocuments         -- what a session carries (staff)
//   requestKycDocumentUrl     -- a short-lived link to one image (staff)
//   fetchVerificationMode / saveVerificationMode -- the platform switch
//
// THE SUBMISSION GOES THROUGH raw fetch(), NOT `api.post`, for the same
// reason company-attachments.ts does: the JSON client sets
// Content-Type: application/json and cannot send FormData. The browser
// fills in the multipart boundary itself, so no Content-Type is set by
// hand here either.
//
// THE FILE TYPE IS CHECKED SERVER-SIDE FROM THE FILENAME EXTENSION, not
// from the Content-Type this browser reports -- that header is
// client-controlled. The client-side check below exists to spare the
// person a round trip and an upload they were never going to keep, not
// as a security boundary.
//
// THE LINK ENDPOINT IS A POST AND THAT IS NOT A TYPO. Issuing a link
// writes an audit row naming the staff member, the person, and the
// object. A GET would be re-fired by any prefetch or refresh and fill
// the audit log with views nobody performed.
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

/** Vocabulary mirrored from backend app/modules/kyc/constants.py
 * (KYCDocumentType). Three literals rather than a generated type: the
 * backend exposes them through the multipart form field, and multipart
 * bodies have no request model for the type generator to emit. */
export type KycDocumentType = 'passport' | 'id_card' | 'driving_licence'

/** Which faces a submission of this type must carry. Mirrors
 * required_document_kinds() in kyc/service.py -- the backend refuses a
 * wrong set regardless; this is what lets the form ask for the right
 * files instead of finding out afterwards. */
export function requiresBackImage(documentType: KycDocumentType): boolean {
  return documentType === 'id_card' || documentType === 'driving_licence'
}

/** Extensions the backend accepts (KYC_EXTENSION_MIME_TYPES). Shorter
 * than the attachment whitelist on purpose: no SVG, no PDF, no WebP,
 * no video. */
export const KYC_ACCEPTED_EXTENSIONS = ['jpg', 'jpeg', 'png'] as const
export const KYC_ACCEPT_ATTRIBUTE = '.jpg,.jpeg,.png'

/** Mirrors KYC_MAX_DOCUMENT_BYTES. */
export const KYC_MAX_DOCUMENT_BYTES = 10 * 1024 * 1024

export interface KycDocument {
  id: string
  kind: 'front' | 'back' | 'selfie'
  content_type: string
  size_bytes: number
  created_at: string
}

export interface KycDocumentUrl {
  url: string
  ttl_seconds: number
}

export interface VerificationModePayload {
  mode: 'manual' | 'automatic'
}

export interface KycSubmitResponse {
  id: string
  status: string
  created_at: string
}

const KYC_UPLOAD_TIMEOUT_MS = 120_000

/** Why a file was rejected before it was ever sent. Returns a
 * translation key, not a sentence: the caller has the locale. */
export function localFileRejection(file: File): string | null {
  const parts = file.name.split('.')
  const extension = parts.length > 1 ? parts[parts.length - 1].toLowerCase() : ''

  if (extension === 'heic' || extension === 'heif') {
    return 'kyc.upload.errorHeic'
  }
  if (!(KYC_ACCEPTED_EXTENSIONS as readonly string[]).includes(extension)) {
    return 'kyc.upload.errorType'
  }
  if (file.size <= 0) {
    return 'kyc.upload.errorEmpty'
  }
  if (file.size > KYC_MAX_DOCUMENT_BYTES) {
    return 'kyc.upload.errorTooLarge'
  }
  return null
}

/**
 * POST /api/v1/kyc/submit -- upload the identity documents, pay the
 * fee, and open a verification session.
 *
 * `backImage` is omitted for a passport and required for the other two
 * types; sending one with a passport is refused server-side, which is
 * why the caller must not pass it "just in case".
 *
 * Error handling mirrors _sendAttachmentMultipart in
 * api/company-attachments.ts -- see that function for the full
 * rationale (ApiTimeoutError on abort, ApiNetworkError on transport
 * failure, ApiResponseError carrying `detail` and Retry-After).
 */
export async function submitKycApplication(
  documentType: KycDocumentType,
  frontImage: File,
  selfieImage: File,
  backImage?: File | null,
): Promise<KycSubmitResponse> {
  const form = new FormData()
  form.append('document_type', documentType)
  form.append('front_image', frontImage)
  form.append('selfie_image', selfieImage)
  if (backImage) {
    form.append('back_image', backImage)
  }

  const headers: Record<string, string> = {}
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), KYC_UPLOAD_TIMEOUT_MS)

  try {
    let response: Response
    try {
      response = await fetch(`${API_BASE_URL}/api/v1/kyc/submit`, {
        method: 'POST',
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

    return data as KycSubmitResponse
  } finally {
    clearTimeout(timeoutId)
  }
}

/** GET /api/v1/staff/kyc/{id}/documents -- what a session carries.
 * An empty array is a real answer: a person approved by hand never
 * submitted anything. */
export function fetchKycDocuments(applicationId: string): Promise<KycDocument[]> {
  return api.get<KycDocument[]>(`/api/v1/staff/kyc/${applicationId}/documents`)
}

/** POST /api/v1/staff/kyc/documents/{id}/url -- a short-lived link.
 * Every call is recorded against the staff member who made it. */
export function requestKycDocumentUrl(
  documentId: string,
): Promise<KycDocumentUrl> {
  return api.post<KycDocumentUrl>(
    `/api/v1/staff/kyc/documents/${documentId}/url`,
    {},
  )
}

/** GET /api/v1/staff/kyc/verification-mode */
export function fetchVerificationMode(): Promise<VerificationModePayload> {
  return api.get<VerificationModePayload>(
    '/api/v1/staff/kyc/verification-mode',
  )
}

/** PUT /api/v1/staff/kyc/verification-mode */
export function saveVerificationMode(
  mode: 'manual' | 'automatic',
): Promise<VerificationModePayload> {
  return api.put<VerificationModePayload>(
    '/api/v1/staff/kyc/verification-mode',
    { mode },
  )
}
