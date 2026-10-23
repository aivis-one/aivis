// =============================================================================
// AIVIS.ONE Frontend -- Documents API (Phase F4.4 B4)
// =============================================================================
//
// Typed wrappers for /api/v1/documents/*.
// Source of truth: backend/app/modules/documents/router.py (Sprint 2.2).
//
// The backend resolves each document to the caller's locale server-side
// (user_language with `en` fallback). Callers receive one row per
// required document type and do not branch on locale. The `is_signed`
// flag on each row reflects the signing state for this specific
// (type, language) pair -- a user who signed `privacy_policy/en` then
// switched to `ru` still counts as signed by type (backend groups by
// type in onboarding progression).
// =============================================================================

import { api, ApiResponseError } from '@/api/client'
import type { DocumentResponse, DocumentSigningResponse } from '@/api/types'

/**
 * GET /api/v1/documents -- list active documents required for the
 * authenticated user's role.
 *
 * One row per type, localised. `is_signed` indicates whether the
 * user has already signed this row.
 */
export function listDocuments(): Promise<DocumentResponse[]> {
  return api.get<DocumentResponse[]>('/api/v1/documents')
}

/**
 * GET /api/v1/documents/{id} -- single document with is_signed flag.
 *
 * Not consumed by the current UI (InvestorDocsView reads from the
 * list), but exposed for symmetry and future use (e.g. deep-link to
 * a specific document).
 */
export function getDocument(id: string): Promise<DocumentResponse> {
  return api.get<DocumentResponse>(`/api/v1/documents/${id}`)
}

/**
 * POST /api/v1/documents/{id}/sign -- record checkbox consent.
 *
 * Backend returns:
 *   201  success
 *   400  document is not in active status (draft or archived)
 *   404  unknown id
 *   409  user already signed this exact row
 *
 * Callers should treat 409 as idempotent success: a concurrent tab
 * or a replayed request produces the same end state.
 */
export function signDocument(id: string): Promise<DocumentSigningResponse> {
  return api.post<DocumentSigningResponse>(`/api/v1/documents/${id}/sign`)
}

/**
 * GET /api/v1/documents/by-type/{type}?lang= -- the current document of a
 * type in `lang` (the caller's language when omitted, English when that
 * language has none). Reaches a document no role has to sign, so it can be
 * read and signed by its id.
 */
export function getDocumentByType(type: string, lang?: string): Promise<DocumentResponse> {
  const qs = lang ? `?lang=${encodeURIComponent(lang)}` : ''
  return api.get<DocumentResponse>(`/api/v1/documents/by-type/${encodeURIComponent(type)}${qs}`)
}

/** How a by-type acceptance ended. */
export type AcceptResult = 'signed' | 'already' | 'missing'

/**
 * Records the caller's acceptance of the current document of a type:
 * reads it by type, signs it unless it is signed already.
 *
 *   'signed'  -- a signing was recorded now
 *   'already' -- the caller had signed it (a 409 counts the same)
 *   'missing' -- no active document of this type exists
 *
 * Any other failure is thrown to the caller.
 */
export async function acceptDocumentByType(type: string, lang?: string): Promise<AcceptResult> {
  let doc: DocumentResponse
  try {
    doc = await getDocumentByType(type, lang)
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 404) return 'missing'
    throw err
  }
  if (doc.is_signed) return 'already'
  try {
    await signDocument(doc.id)
  } catch (err) {
    if (err instanceof ApiResponseError && err.status === 409) return 'already'
    throw err
  }
  return 'signed'
}
