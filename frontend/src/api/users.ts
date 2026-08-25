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
import type { PayoutDetailsResponse, UserResponse, UserUpdate } from '@/api/types'

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
