// =============================================================================
// AIVIS.ONE Frontend -- Users API (Phase F4.4 B5 + F5.2 B3)
// =============================================================================
//
// Typed wrappers for /api/v1/users/me + /me/payout-details.
// Source of truth: backend/app/modules/users/router.py
//   - Sprint 1.3 + F2.3  -- /me (GET, PATCH)
//   - Sprint 6.3         -- /me/payout-details (GET, PUT)
//
// Until F4.4 B5 the only consumers of /me were inline `api.get/patch`
// calls inside OnboardingProfileView and auth/store. F4.4 B5 added
// the typed wrappers; F5.2 B3 extends the same module with
// payout-details so company balance flows have a typed surface (the
// onboarding view migration is still TD-F13).
//
// FIELD CONTRACT NOTES (UserUpdate).
//   { profile?, language? }, partial semantics (exclude_unset on
//   the backend). profile merges with existing JSONB server-side via
//   set_jsonb; callers send only the keys they change. Allowed
//   profile keys as of B5: first_name, last_name, country, phone,
//   avatar_url, marketing_consent. Unknown keys -> 400.
//   language is NOT NULL -- explicit null -> 400.
//
// FIELD CONTRACT NOTES (payout-details).
//   payout_details on the backend is a free-form JSONB blob (P6-32);
//   no key whitelist, future payment-provider integration will land
//   the schema. PUT replaces the value wholesale -- not a merge.
//   GET returns { payout_details: dict | null }; null when the user
//   has not set details yet.
// =============================================================================

import { api } from '@/api/client'
import type {
  ConfirmEmailChangeRequest,
  DeactivateAccountRequest,
  PayoutDetailsResponse,
  RequestEmailChangeRequest,
  UserResponse,
  UserUpdate,
} from '@/api/types'

/**
 * GET /api/v1/users/me -- authenticated user profile.
 */
export function getMe(): Promise<UserResponse> {
  return api.get<UserResponse>('/api/v1/users/me')
}

/**
 * PATCH /api/v1/users/me -- partial update.
 *
 * Only keys present in `body` are applied. Returns the full updated
 * UserResponse so callers can sync the auth store without a second
 * GET round-trip (see InvestorSettingsView marketing toggle).
 */
export function updateMe(body: UserUpdate): Promise<UserResponse> {
  return api.patch<UserResponse>('/api/v1/users/me', body)
}

/**
 * GET /api/v1/users/me/payout-details -- read withdrawal payout
 * methods configured by the user.
 *
 * Returns { payout_details: null } when nothing has been configured
 * yet -- callers render an empty state rather than treating this as
 * an error.
 */
export function getPayoutDetails(): Promise<PayoutDetailsResponse> {
  return api.get<PayoutDetailsResponse>('/api/v1/users/me/payout-details')
}

/**
 * PUT /api/v1/users/me/payout-details -- replace payout methods.
 *
 * Free-form JSONB blob -- no whitelist on the backend (Sprint 6.3
 * P6-32). Replaces the value wholesale. Audit event
 * `user.payout_details_updated` fires with `data={}` (sensitive
 * details are not logged).
 */
export function updatePayoutDetails(
  payout_details: Record<string, unknown>,
): Promise<PayoutDetailsResponse> {
  return api.put<PayoutDetailsResponse>('/api/v1/users/me/payout-details', { payout_details })
}

// ---------------------------------------------------------------------------
// Email change (TASK-38)
// ---------------------------------------------------------------------------
//
// Three-step flow -- see users/schemas.py's "Email change" section for
// the full contract:
//   1. requestEmailChange -- current password + new email. Sends a
//      6-digit code to the NEW address. Rate-limited server-side via
//      the shared auth_rate_limit_max_requests/window_seconds default
//      (5 per 60s out of the box, not a bespoke 1) under key
//      email_change_request:{user.id}.
//   2. resendEmailChangeCode -- regenerate + resend. Same rate limit
//      family, its own key (email_change_resend:{user.id}).
//   3. confirmEmailChange -- the 6-digit code. On success the login
//      email has already moved server-side; the caller's own session
//      stays valid (unlike a password reset, nothing is invalidated).

/**
 * POST /api/v1/users/me/email-change -- request an email change.
 *
 * 204 No Content on success (no body). Throws ApiResponseError on:
 *   403 incorrect_password -- current_password did not match.
 *   400 -- new_email equals the current login email.
 *   409 -- new_email already belongs to another account.
 *   429 -- rate limited.
 */
export function requestEmailChange(body: RequestEmailChangeRequest): Promise<void> {
  return api.post<void>('/api/v1/users/me/email-change', body)
}

/**
 * POST /api/v1/users/me/email-change/resend -- resend the pending code.
 *
 * 204 No Content on success. Throws ApiResponseError on:
 *   400 -- no pending email change on this account.
 *   429 -- rate limited.
 */
export function resendEmailChangeCode(): Promise<void> {
  return api.post<void>('/api/v1/users/me/email-change/resend', {})
}

/**
 * POST /api/v1/users/me/email-change/confirm -- confirm with the code.
 *
 * Returns the updated UserResponse (email already moved) so the caller
 * can sync the auth store the same way updateMe() does. Throws
 * ApiResponseError on:
 *   400 -- no pending change, expired, too many attempts, or wrong code.
 *   409 -- the pending email was claimed by another account in the interim.
 */
export function confirmEmailChange(body: ConfirmEmailChangeRequest): Promise<UserResponse> {
  return api.post<UserResponse>('/api/v1/users/me/email-change/confirm', body)
}

// ---------------------------------------------------------------------------
// Self-deactivation (TASK-38)
// ---------------------------------------------------------------------------

/**
 * POST /api/v1/users/me/deactivate -- self-deactivate the account.
 *
 * Soft/reversible: is_active=False + a "self" discriminator server-side
 * (see users/service.py). Kills every session, including the one that
 * made this call -- the caller should treat any response (success or
 * not) as "assume logged out" and clear local session state, mirroring
 * how confirm_password_reset's frontend counterpart behaves. 204 No
 * Content on success. Throws ApiResponseError on:
 *   403 incorrect_password -- current_password did not match.
 *   400 -- staff/platform accounts cannot self-deactivate.
 */
export function deactivateAccount(body: DeactivateAccountRequest): Promise<void> {
  return api.post<void>('/api/v1/users/me/deactivate', body)
}
