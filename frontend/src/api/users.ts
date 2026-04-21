// =============================================================================
// CBSHOME Frontend -- Users API (Phase F4.4 B5)
// =============================================================================
//
// Typed wrappers for /api/v1/users/me.
// Source of truth: backend/app/modules/users/router.py (Sprint 1.3 + F2.3).
//
// Until B5 the only consumers of these endpoints were inline
// `api.get/patch` calls inside OnboardingProfileView and auth/store.
// InvestorSettingsView needs at least updateMe(), so the module lands
// now. The onboarding view is NOT migrated in B5 to keep the diff
// scoped -- a follow-up refactor can switch it over without touching
// behaviour.
//
// FIELD CONTRACT NOTES.
//   UserUpdate accepts { profile?, language? } with partial semantics
//   (exclude_unset on the backend). profile merges with existing JSONB
//   server-side via set_jsonb; callers send only the keys they change.
//   Allowed profile keys as of B5: first_name, last_name, country,
//   phone, avatar_url, marketing_consent. Unknown keys -> 400.
//   language is NOT NULL -- explicit null -> 400.
// =============================================================================

import { api } from '@/api/client'
import type { UserResponse, UserUpdate } from '@/api/types'

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
