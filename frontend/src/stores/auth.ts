// =============================================================================
// CBSHOME Frontend -- Auth Store (Pinia)
// =============================================================================
//
// Manages authentication state: user, token, role.
// Token persisted via platform.getStorageDriver() under key 'cbs_token'.
// Registers _onUnauthorized callback in API client.
// =============================================================================

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

import { api, setAuthToken, setOnUnauthorized } from '@/api/client'
import type { AuthResponse, UserResponse, UserRole } from '@/api/types'
import { platform } from '@/platform'

const TOKEN_KEY = 'cbs_token'

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
  const role = computed<UserRole | null>(() => user.value?.role ?? null)

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
  }

  function _clearSession(): void {
    _persistToken(null)
    user.value = null
  }

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  async function loginViaEmail(email: string, password: string): Promise<void> {
    loading.value = true
    try {
      const response = await api.post<AuthResponse>('/api/v1/auth/email/login', {
        email,
        password,
      })
      _setSession(response)
    } finally {
      loading.value = false
    }
  }

  async function registerViaEmail(
    email: string,
    password: string,
    referralCode?: string | null,
  ): Promise<void> {
    loading.value = true
    try {
      const response = await api.post<AuthResponse>('/api/v1/auth/email/register', {
        email,
        password,
        referral_code: referralCode || undefined,
      })
      _setSession(response)
      // Clear referral code after successful registration.
      sessionStorage.removeItem('cbs_referral_code')
    } finally {
      loading.value = false
    }
  }

  async function loginViaTelegram(
    initData: string,
    referralCode?: string | null,
  ): Promise<void> {
    loading.value = true
    try {
      const response = await api.post<AuthResponse>('/api/v1/auth/telegram', {
        init_data: initData,
        referral_code: referralCode || undefined,
      })
      _setSession(response)
      sessionStorage.removeItem('cbs_referral_code')
    } finally {
      loading.value = false
    }
  }

  /** Try to restore session from persisted token. Returns true on success. */
  async function restoreSession(): Promise<boolean> {
    const storage = _getStorage()
    const savedToken = storage.getItem(TOKEN_KEY)
    if (!savedToken) return false

    // Set token first so API client can send it.
    _persistToken(savedToken)
    try {
      user.value = await api.get<UserResponse>('/api/v1/users/me')
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
    loginViaEmail,
    registerViaEmail,
    loginViaTelegram,
    restoreSession,
    fetchMe,
    logout,
  }
})
