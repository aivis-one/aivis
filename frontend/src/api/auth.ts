// =============================================================================
// AIVIS.ONE Frontend -- Auth API (TASK-38)
// =============================================================================
//
// Typed wrappers for the "manage your active sessions" pair added
// alongside the existing logout / logout-all flows (those two stay
// inline in stores/auth.ts -- logout is tightly coupled to session
// clearing there; these two are read/act-on-a-list calls with no
// local-session-clearing side effect of their own, so they live here
// instead, matching api/users.ts's shape for the sibling
// email-change / deactivate-account TASK-38 endpoints).
//
// session_id (both functions) is NEVER the bearer token -- it is a
// non-reversible id derived server-side (SHA-256 of the token, see
// backend/app/modules/auth/service.py's "PUBLIC SESSION ID" module
// note). Holding it grants no access; it only identifies which
// session DELETE should target.
// =============================================================================

import { api } from '@/api/client'
import type { SessionListResponse } from '@/api/types'

/**
 * GET /api/v1/auth/sessions -- list the caller's own active sessions,
 * newest first. Each item carries created_at / auth_method / ip /
 * user_agent plus is_current (true for the session making this call).
 */
export function listSessions(): Promise<SessionListResponse> {
  return api.get<SessionListResponse>('/api/v1/auth/sessions')
}

/**
 * DELETE /api/v1/auth/sessions/{sessionId} -- revoke one session by
 * its public id. 204 No Content on success. Throws ApiResponseError on:
 *   404 -- sessionId does not belong to the caller (never distinguishes
 *          "does not exist" from "belongs to someone else").
 *   403 -- avatar mode (forbid_avatar("revoke_session"), see
 *          auth/avatar_guard.py's revoke_session note).
 */
export function revokeSession(sessionId: string): Promise<void> {
  return api.delete(`/api/v1/auth/sessions/${encodeURIComponent(sessionId)}`)
}
