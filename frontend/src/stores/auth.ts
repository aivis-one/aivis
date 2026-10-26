// =============================================================================
// AIVIS.ONE Frontend -- Auth Store (Pinia)
// =============================================================================
//
// Manages authentication state: user, token, role.
// Token persisted via platform.getStorageDriver() under key 'aivis_token'.
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
import { verifyTwoFactorLogin } from '@/api/auth'
import {
  asKycStatus,
  asUserRole,
  type AuthResponse,
  type KycStatus,
  type LoginResponse,
  type TelegramLinkEmailResponse,
  type UserResponse,
  type UserRole,
} from '@/api/types'
import { platform } from '@/platform'
import { setAvatarActive } from '@/composables/avatarState'
import { i18n, setLocale } from '@/i18n'
import { resetAllDataStores } from '@/stores/sessionReset'

/**
 * Discriminated result of loginViaEmail / loginViaTelegram (TASK-38).
 *
 * Both used to be `Promise<void>` -- a resolved promise always meant
 * "signed in". With 2FA, a resolved promise now means "the password
 * (or Telegram identity) checked out", which is a real but incomplete
 * outcome: `mfaRequired: true` means NO session exists yet, and the
 * caller must drive the caller-visible code-entry step (LoginView.vue)
 * before calling completeMfaLogin() with the returned `mfaToken`.
 */
export type LoginResult = { mfaRequired: false } | { mfaRequired: true; mfaToken: string }

/**
 * Result of loginViaTelegram: a LoginResult, or `linkRequired` when no account
 * holds this Telegram id yet. In that case no session exists; the store keeps
 * the link token (memory only) and the entry screen finishes the sign-in with
 * sendTelegramLinkEmail / confirmTelegramLink.
 */
export type TelegramLoginResult = LoginResult | { mfaRequired: false; linkRequired: true }

const TOKEN_KEY = 'aivis_token'

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
export const REFERRAL_KEY = 'aivis_referral_code'

export const useAuthStore = defineStore('auth', () => {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  const user = ref<UserResponse | null>(null)
  const token = ref<string | null>(null)
  const loading = ref(false)

  // Telegram entry state. Both tokens are short-lived and live in memory only:
  // never written to a storage, gone with the tab.
  //   telegramLinkToken -- from POST /auth/telegram when the Telegram id is new.
  //   telegramMfaToken  -- from POST /auth/telegram when the account has
  //                        two-factor on; completes with completeMfaLogin.
  const telegramLinkToken = ref<string | null>(null)
  const telegramMfaToken = ref<string | null>(null)

  // ---------------------------------------------------------------------------
  // Computed
  // ---------------------------------------------------------------------------

  const isAuthenticated = computed(() => !!token.value && !!user.value)

  // Sprint 4.4: role / kycStatus pass through narrowing guards from
  // api/types.ts. Unknown values become `null`, never an unsafe cast.
  const role = computed<UserRole | null>(() => asUserRole(user.value?.role))
  const kycStatus = computed<KycStatus | null>(() => asKycStatus(user.value?.kyc_status))

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  function _getStorage(): Storage {
    return platform.getStorageDriver() === 'sessionStorage' ? sessionStorage : localStorage
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

  /**
   * A login response carries no staff_profile (only GET /users/me builds
   * it), so a staff member who signs in would see every right as false and
   * a menu without Finance or Platform. After a staff sign-in the profile is
   * read once more before the caller moves on. A failed read keeps the
   * sign-in: the session is real, the next /users/me read fills the rights.
   */
  async function _completeSession(response: AuthResponse): Promise<void> {
    _setSession(response)
    if (response.user?.role !== 'staff') return
    try {
      const me = await api.get<UserResponse>('/api/v1/users/me')
      if (me && me.id === response.user.id) user.value = me
    } catch {
      // Keep the session from the login response.
    }
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

  /**
   * Email + password login (TASK-38: now 2FA-aware).
   *
   * Resolves to `{ mfaRequired: false }` after a real session is
   * established (referral cleanup + _setSession run exactly as
   * before), or `{ mfaRequired: true, mfaToken }` when the account has
   * 2FA enabled -- in that branch NO session is created and the
   * referral code is deliberately left untouched (the login has not
   * actually completed yet; clearing it here would burn the one-shot
   * credit before the visitor ever finishes signing in). The caller
   * (LoginView.vue) shows a code-entry step and calls
   * completeMfaLogin() with the token.
   */
  async function loginViaEmail(email: string, password: string): Promise<LoginResult> {
    loading.value = true
    try {
      const response = await api.post<LoginResponse>('/api/v1/auth/email/login', {
        email,
        password,
      })
      if (response.mfa_required) {
        return { mfaRequired: true, mfaToken: response.mfa_token as string }
      }
      await _completeSession(response as AuthResponse)
      // iter 2.6 batch 2: clear the one-shot referral code on
      // successful sign-in. Closes the hygiene gap where a visitor
      // who followed a referral link but then signed into an existing
      // account left a stale code lingering in their tab. Matches the
      // cleanup already done by registerViaEmail / loginViaTelegram.
      sessionStorage.removeItem(REFERRAL_KEY)
      return { mfaRequired: false }
    } finally {
      loading.value = false
    }
  }

  /**
   * TASK-38: complete a 2FA-gated login. Call after loginViaEmail /
   * loginViaTelegram resolved with `mfaRequired: true`, once the
   * caller has a live code (or an unused backup code) from the user.
   *
   * On success, establishes a real session exactly like a normal
   * login (_setSession + referral cleanup -- this IS the point where
   * the login actually completes, so the one-shot referral credit is
   * consumed here instead of at the mfa_required branch above).
   *
   * Throws ApiResponseError on a wrong/expired code or an
   * invalid/expired mfa_token (400) -- see api/auth.ts's
   * verifyTwoFactorLogin docstring for why a retry needs a FRESH
   * mfa_token, not the same one again.
   */
  async function completeMfaLogin(mfaToken: string, code: string): Promise<void> {
    loading.value = true
    try {
      const response = await verifyTwoFactorLogin({ mfa_token: mfaToken, code })
      await _completeSession(response)
      telegramMfaToken.value = null
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
        {
          email,
          password,
          referral_code: referralCode || null,
          // The interface language chosen on the register screen: the
          // first verification letter goes out in it.
          language: i18n.global.locale.value,
        },
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

  /**
   * Telegram WebApp login (TASK-38: now 2FA-aware).
   *
   * A Telegram-linked account can independently have email+password+2FA
   * configured -- upsert_telegram_user (backend) never touches
   * credentials.totp, so gating only the email/password path would
   * leave a real bypass. Same mfaRequired branch as loginViaEmail; the
   * token is kept in `telegramMfaToken` for the Mini App's second-code
   * screen (views/auth/TelegramSecondCodeView.vue).
   *
   * The endpoint creates no account. A Telegram id nobody holds gets
   * `link_required` and a link token: the result is `linkRequired` and the
   * entry screen (views/auth/TelegramEntryView.vue) takes over.
   */
  async function loginViaTelegram(
    initData: string,
    referralCode?: string | null,
  ): Promise<TelegramLoginResult> {
    loading.value = true
    try {
      const response = await api.post<LoginResponse>(
        '/api/v1/auth/telegram',
        // `|| null` -- same rationale as registerViaEmail above.
        { init_data: initData, referral_code: referralCode || null },
      )
      if (response.link_required) {
        telegramLinkToken.value = response.link_token ?? null
        telegramMfaToken.value = null
        return { mfaRequired: false, linkRequired: true }
      }
      if (response.mfa_required) {
        telegramMfaToken.value = response.mfa_token as string
        telegramLinkToken.value = null
        return { mfaRequired: true, mfaToken: response.mfa_token as string }
      }
      await _completeSession(response as AuthResponse)
      telegramLinkToken.value = null
      telegramMfaToken.value = null
      // Same cleanup as the email register path: the referral code is one-shot.
      sessionStorage.removeItem(REFERRAL_KEY)
      return { mfaRequired: false }
    } finally {
      loading.value = false
    }
  }

  /**
   * Telegram entry, e-mail step: ask the server to send a code to `email`.
   * Called only after the person ticked both documents (consent_given). The
   * server answers the same way for every address, so a resolved promise says
   * nothing about the address. Throws ApiResponseError, e.g. `link_token_invalid`
   * (the link expired) or 429 `telegram_link_locked` / `telegram_link_emails_per_day`.
   */
  async function sendTelegramLinkEmail(
    email: string,
    referralCode?: string | null,
  ): Promise<TelegramLinkEmailResponse> {
    if (!telegramLinkToken.value) {
      throw new Error('No Telegram link token')
    }
    loading.value = true
    try {
      return await api.post<TelegramLinkEmailResponse>('/api/v1/auth/telegram/link/email', {
        link_token: telegramLinkToken.value,
        email,
        consent_given: true,
        // `|| null` -- same rationale as registerViaEmail above.
        referral_code: referralCode || null,
      })
    } finally {
      loading.value = false
    }
  }

  /**
   * Telegram entry, code step: prove the mailbox with the 6-digit code (and the
   * second code when the account has two-factor on) and link the Telegram id.
   * On success the session is set exactly as a normal login sets it. Throws
   * ApiResponseError: `second_code_required` asks for the authenticator code
   * (call again with it), `invalid_code`, `code_expired`, `link_token_invalid`.
   */
  async function confirmTelegramLink(code: string, secondCode?: string | null): Promise<void> {
    if (!telegramLinkToken.value) {
      throw new Error('No Telegram link token')
    }
    loading.value = true
    try {
      const response = await api.post<AuthResponse>('/api/v1/auth/telegram/link/confirm', {
        link_token: telegramLinkToken.value,
        code,
        second_code: secondCode || null,
      })
      await _completeSession(response)
      telegramLinkToken.value = null
      sessionStorage.removeItem(REFERRAL_KEY)
    } finally {
      loading.value = false
    }
  }

  /** Forget the Telegram entry's tokens (an expired link, a consumed second-code token). */
  function clearTelegramEntry(): void {
    telegramLinkToken.value = null
    telegramMfaToken.value = null
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

  /**
   * Ends every session of the user on every device, then clears this one.
   * Unlike logout(), a failure is NOT swallowed: the local session is cleared
   * only after the server has ended them all, so the screen never claims that
   * other devices were signed out when they were not.
   */
  async function logoutAllDevices(): Promise<void> {
    await api.post<void>('/api/v1/auth/logout-all')
    _clearSession()
  }

  // ---------------------------------------------------------------------------
  // Register 401 callback
  // ---------------------------------------------------------------------------
  //
  // The 402 callback (setOnKycRequired) is wired in main.ts instead of
  // here: reaching the router from this store would mean importing it,
  // and the router imports every view, which imports this store. The
  // pre-auth width check follows those imports and saw the cycle
  // before a browser could.

  setOnUnauthorized(() => _clearSession())

  // ---------------------------------------------------------------------------
  // Expose
  // ---------------------------------------------------------------------------

  return {
    user,
    token,
    loading,
    telegramLinkToken,
    telegramMfaToken,
    isAuthenticated,
    role,
    kycStatus,
    loginViaEmail,
    completeMfaLogin,
    registerViaEmail,
    loginViaTelegram,
    sendTelegramLinkEmail,
    confirmTelegramLink,
    clearTelegramEntry,
    restoreSession,
    fetchMe,
    logout,
    logoutAllDevices,
  }
})
