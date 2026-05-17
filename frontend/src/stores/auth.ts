// =============================================================================
// CBSHOME Frontend -- Auth Store (Pinia)
// =============================================================================
//
// Manages authentication state: user, token, role.
// Token persisted via platform.getStorageDriver() under key 'cbs_token'.
// Registers _onUnauthorized callback in API client.
//
// Sprint 4.4 (post-VELO hardening):
//   `role` is now exposed as `UserRole | null`, not `string | null`.
//   The narrowing happens through `asUserRole` (api/types.ts) which
//   returns `null` for unknown values rather than an unsafe cast --
//   that means `authStore.role === 'investor'` checks across the
//   codebase get a typo guard (compile-time error if the literal isn't
//   a member of UserRole) without any runtime-typed-cast tricks.
//
//   New computed `kycStatus: KycStatus | null` mirrors the same shape
//   for KYC-gated checks (purchase, agent application). Callers like
//   InvestorSettingsView can drop their inline `=== 'approved'` raw
//   comparisons in favour of `authStore.kycStatus === 'approved'`,
//   typed.
//
//   Router guards still receive a string-compatible value (UserRole is
//   a subset of string) so the existing `roles?: string[]` route meta
//   contract works without changes.
//
// F5.1 B1 -- session reset wiring:
//   _clearSession() now calls resetAllDataStores() and explicitly
//   clears `loading`. Before this commit, every data store's
//   `reset()` existed but was never called -- a logout / 401 left
//   user A's dashboard, portfolio, transactions etc. sitting in
//   memory until B's first onMounted refresh overwrote them, with
//   a brief render window where B could see A's financial state.
//   In addition, an in-flight fetch resolving AFTER _clearSession()
//   would write A's data back into the surviving store because
//   nothing bumped the FP-17 epoch on logout. The reset() calls
//   close both holes (each one bumps its store's epoch first).
//   `loading.value = false` covers a parallel gap: a 401 firing
//   while loginViaEmail / registerViaEmail / loginViaTelegram is
//   awaiting would have left `loading` pinned to true forever,
//   freezing every spinner-gated UI element. See sessionReset.ts
//   header for the why-a-helper rationale.
//
// iter 2.6 batch 2 -- referral cleanup on email login:
//   loginViaEmail() now clears the referral key from sessionStorage
//   on success, matching registerViaEmail() and loginViaTelegram().
//   Previously this was the only path that did not, so a visitor who
//   followed a referral link and then logged into an EXISTING account
//   left a stale code lingering in their tab. A subsequent registration
//   in the same tab would silently consume it -- minor but
//   inconsistent. NOT cleared from _clearSession(): a 401 / logout
//   should preserve the referral so the visitor can register a fresh
//   account under the same agent without losing attribution.
//
// iter 2.6 R22 STYLE-22-01:
//   REFERRAL_KEY is exported from this module as the single source of
//   truth. composables/useAuth.ts imports it (and uses it for the
//   first-wins guard + capture writes); views/auth/LoginView.vue
//   imports it for the post-sign-in cleanup. Living here avoids the
//   circular-import shape that would arise if the constant lived in
//   useAuth.ts (useAuth -> stores/auth for useAuthStore, and back
//   would close the cycle). The auth store is the natural owner since
//   it does three of the four call-sites (clearing on each successful
//   login flow).
// =============================================================================

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

import { api, setAuthToken, setOnUnauthorized } from '@/api/client'
import {
  asKycStatus,
  asUserRole,
  type AuthResponse,
  type KycStatus,
  type UserResponse,
  type UserRole,
} from '@/api/types'
import { platform } from '@/platform'
import { setAvatarActive } from '@/composables/avatarState'
import { setLocale } from '@/i18n'
import { resetAllDataStores } from '@/stores/sessionReset'

const TOKEN_KEY = 'cbs_token'

/**
 * sessionStorage key for the one-shot referral code captured per
 * browser-tab session (FP-13 first-wins). Single source of truth --
 * imported by composables/useAuth.ts for the capture write and by
 * views/auth/LoginView.vue for post-sign-in cleanup.
 *
 * NOT removed from _clearSession(): a 401 / logout in a tab that
 * arrived via a referral link should preserve the credit so the
 * visitor can register a fresh account under the same agent.
 */
export const REFERRAL_KEY = 'cbs_referral_code'

export const useAuthStore = defineStore('auth', () => {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  const user = ref<UserResponse | null>(null)
  const token = ref<string | null>(null)
  const loading = ref(false)

  // ---------------------------------------------------------------------------
  // Computed
  // ---------------------------------------------------------------------------

  const isAuthenticated = computed(() => !!token.value && !!user.value)

  // Sprint 4.4: role / kycStatus pass through narrowing guards from
  // api/types.ts. Unknown values become `null`, never an unsafe cast.
  const role = computed<UserRole | null>(
    () => asUserRole(user.value?.role),
  )
  const kycStatus = computed<KycStatus | null>(
    () => asKycStatus(user.value?.kyc_status),
  )

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  function _getStorage(): Storage {
    return platform.getStorageDriver() === 'sessionStorage'
      ? sessionStorage
      : localStorage
  }

  function _persistToken(value: string | null): void {
    token.value = value
    setAuthToken(value)
    const storage = _getStorage()
    if (value) {
      storage.setItem(TOKEN_KEY, value)
    } else {
      storage.removeItem(TOKEN_KEY)
    }
  }

  function _setSession(response: AuthResponse): void {
    _persistToken(response.session_token)
    user.value = response.user
    // Backend is the source of truth for user.language; sync the UI.
    // Fire-and-forget: locale JSON loads lazily, no need to await.
    void setLocale(response.user.language)
  }

  function _clearSession(): void {
    // Clear `loading` first. If a login / register / restoreSession
    // is mid-flight and a 401 fires the unauthorized callback, the
    // in-flight promise still resolves to its `finally` block and
    // would set loading=false anyway -- but so might a brand-new
    // login attempt that started AFTER the callback fired. Setting
    // it false up-front gives spinner-gated UI a clean baseline.
    loading.value = false
    _persistToken(null)
    user.value = null
    // Reset avatar flag + clean sessionStorage marker.
    setAvatarActive(false)
    // Drop every data store so user A's state cannot bleed into
    // user B's session in the same tab. Each store's reset() bumps
    // its FP-17 epoch first -- in-flight fetches that resolve after
    // us drop silently instead of repopulating the cleared state.
    // No circular import risk: see sessionReset.ts header.
    resetAllDataStores()
    // NOTE: see REFERRAL_KEY JSDoc for why we deliberately do NOT
    // remove the referral key here.
  }

  // ---------------------------------------------------------------------------
  // Login flows
  // ---------------------------------------------------------------------------

  /** Email + password login. */
  async function loginViaEmail(
    email: string,
    password: string,
  ): Promise<void> {
    loading.value = true
    try {
      const response = await api.post<AuthResponse>(
        '/api/v1/auth/email/login',
        { email, password },
      )
      _setSession(response)
      // iter 2.6 batch 2: clear the one-shot referral code on
      // successful sign-in. Closes the hygiene gap where a visitor
      // who followed a referral link but then signed into an existing
      // account left a stale code lingering in their tab. Matches the
      // cleanup already done by registerViaEmail / loginViaTelegram.
      sessionStorage.removeItem(REFERRAL_KEY)
    } finally {
      loading.value = false
    }
  }

  /** Email + password registration. */
  async function registerViaEmail(
    email: string,
    password: string,
    referralCode?: string | null,
  ): Promise<void> {
    loading.value = true
    try {
      const response = await api.post<AuthResponse>(
        '/api/v1/auth/email/register',
        // `|| null` (not `?? null`) so an empty referralCode "" is
        // treated as missing rather than sent to the backend as the
        // literal "" -- the backend's referral_code field has no
        // min_length, so empty string would silently masquerade as a
        // valid (always-missed) referral lookup.
        { email, password, referral_code: referralCode || null },
      )
      _setSession(response)
      // Clear referral code after successful registration.
      // Without this, the next register/login in the same browser
      // session would re-attribute under the same referrer (commission
      // duplication on the agent payout side).
      sessionStorage.removeItem(REFERRAL_KEY)
    } finally {
      loading.value = false
    }
  }

  /** Telegram WebApp login. */
  async function loginViaTelegram(
    initData: string,
    referralCode?: string | null,
  ): Promise<void> {
    loading.value = true
    try {
      const response = await api.post<AuthResponse>(
        '/api/v1/auth/telegram',
        // `|| null` -- same rationale as registerViaEmail above.
        { init_data: initData, referral_code: referralCode || null },
      )
      _setSession(response)
      // Same cleanup as the email register path -- the Telegram login
      // endpoint also creates a User on first call (when there is no
      // matching telegram credential), so the referral attribution
      // applies and must be one-shot.
      sessionStorage.removeItem(REFERRAL_KEY)
    } finally {
      loading.value = false
    }
  }

  // ---------------------------------------------------------------------------
  // Session persistence
  // ---------------------------------------------------------------------------

  /**
   * Restore persisted session from storage. Returns true if a valid
   * session was restored, false otherwise (storage empty or token
   * rejected by /users/me).
   */
  async function restoreSession(): Promise<boolean> {
    const storage = _getStorage()
    const stored = storage.getItem(TOKEN_KEY)
    if (!stored) return false

    _persistToken(stored)
    try {
      const me = await api.get<UserResponse>('/api/v1/users/me')
      user.value = me
      void setLocale(me.language)
      return true
    } catch {
      _clearSession()
      return false
    }
  }

  /** Refresh user profile from backend. */
  async function fetchMe(): Promise<void> {
    user.value = await api.get<UserResponse>('/api/v1/users/me')
  }

  async function logout(): Promise<void> {
    try {
      await api.post<void>('/api/v1/auth/logout')
    } catch {
      // Ignore errors during logout -- clear session regardless.
    } finally {
      _clearSession()
    }
  }

  // ---------------------------------------------------------------------------
  // Register 401 callback
  // ---------------------------------------------------------------------------

  setOnUnauthorized(() => _clearSession())

  // ---------------------------------------------------------------------------
  // Expose
  // ---------------------------------------------------------------------------

  return {
    user,
    token,
    loading,
    isAuthenticated,
    role,
    kycStatus,
    loginViaEmail,
    registerViaEmail,
    loginViaTelegram,
    restoreSession,
    fetchMe,
    logout,
  }
})
