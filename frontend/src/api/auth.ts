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
import type {
  AuthResponse,
  SessionListResponse,
  TwoFactorConfirmRequest,
  TwoFactorConfirmResponse,
  TwoFactorDisableRequest,
  TwoFactorLoginVerifyRequest,
  TwoFactorSetupRequest,
  TwoFactorSetupResponse,
} from '@/api/types'

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

// ---------------------------------------------------------------------------
// Two-Factor Authentication (TOTP) -- TASK-38
// ---------------------------------------------------------------------------
//
// Source of truth: backend/app/modules/auth/router.py "Two-Factor
// Authentication (TOTP)" section + schemas.py. `stores/auth.ts` owns
// the LOGIN-TIME half (loginViaEmail/loginViaTelegram detecting
// mfa_required, completeMfaLogin calling the verify endpoint below) --
// these four wrappers are the account-management half, called from
// components/shared/TwoFactorSection.vue.

/**
 * POST /api/v1/auth/2fa/setup -- start (or restart) TOTP setup.
 * Requires the current password. Returns the raw secret (shown once,
 * for manual entry) plus a provisioning_uri to render as a QR code.
 * Throws ApiResponseError on:
 *   403 incorrect_password -- current_password did not match.
 *   429 -- rate limited.
 */
export function setupTwoFactor(body: TwoFactorSetupRequest): Promise<TwoFactorSetupResponse> {
  return api.post<TwoFactorSetupResponse>('/api/v1/auth/2fa/setup', body)
}

/**
 * POST /api/v1/auth/2fa/confirm -- confirm setup with a live code.
 *
 * On success, 2FA is switched ON and backup_codes are returned --
 * ONCE. There is no endpoint to retrieve them again; the caller MUST
 * treat this response as a "save these now" moment. Throws
 * ApiResponseError on:
 *   400 -- no pending setup, or the code did not verify (2FA stays off).
 *   429 -- rate limited.
 */
export function confirmTwoFactor(
  body: TwoFactorConfirmRequest,
): Promise<TwoFactorConfirmResponse> {
  return api.post<TwoFactorConfirmResponse>('/api/v1/auth/2fa/confirm', body)
}

/**
 * POST /api/v1/auth/2fa/disable -- turn 2FA off.
 *
 * Requires BOTH the current password AND a live TOTP code or an
 * unused backup code -- either alone is rejected. 204 No Content on
 * success. Throws ApiResponseError on:
 *   403 incorrect_password -- current_password did not match.
 *   400 -- 2FA is not enabled, or the code did not verify.
 *   429 -- rate limited.
 */
export function disableTwoFactor(body: TwoFactorDisableRequest): Promise<void> {
  return api.post<void>('/api/v1/auth/2fa/disable', body)
}

/**
 * POST /api/v1/auth/2fa/login-verify -- complete a 2FA-gated login.
 *
 * UNAUTHENTICATED (no Authorization header sent -- the api client only
 * adds one when a token is set, and none exists at this point). Takes
 * the mfa_token from a LoginResponse(mfa_required=true) plus a live
 * code or unused backup code; on success returns a real AuthResponse
 * (same shape as a normal login/register). Throws ApiResponseError on:
 *   400 -- invalid/expired token, or the code did not verify. The
 *          pending token is consumed either way -- a retry with the
 *          SAME mfa_token, even with the correct code, will also fail;
 *          the caller must sign in again to get a fresh token.
 *   429 -- rate limited (tighter than the default auth rate limit,
 *          see the backend docstring for why).
 */
export function verifyTwoFactorLogin(body: TwoFactorLoginVerifyRequest): Promise<AuthResponse> {
  return api.post<AuthResponse>('/api/v1/auth/2fa/login-verify', body)
}
