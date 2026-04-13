import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import { platform } from '@/platform'
import type { UserResponse } from '@/api/types'
import { UnauthorizedError } from '@/api/types'

const TOKEN_KEY = 'auth_token'

function getStorage(): Storage {
  return platform.type === 'telegram' ? sessionStorage : localStorage
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserResponse | null>(null)
  const token = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const userRole = computed(() => user.value?.role ?? null)

  function setAuth(sessionToken: string, profile: UserResponse) {
    token.value = sessionToken
    user.value = profile
    getStorage().setItem(TOKEN_KEY, sessionToken)
  }

  function clearAuth() {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(TOKEN_KEY)
  }

  async function login(email: string, password: string) {
    loading.value = true
    error.value = null
    try {
      const response = await authApi.login({ email, password })
      setAuth(response.session_token, response.user)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Login failed'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function register(email: string, password: string) {
    loading.value = true
    error.value = null
    try {
      const response = await authApi.register({ email, password })
      setAuth(response.session_token, response.user)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Registration failed'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function telegramAuth() {
    const tg = window.Telegram?.WebApp
    if (!tg?.initData) {
      throw new Error('Telegram WebApp not available')
    }
    loading.value = true
    error.value = null
    try {
      const response = await authApi.telegramAuth({ init_data: tg.initData })
      setAuth(response.session_token, response.user)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Telegram auth failed'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch {
      // Clear local state regardless of API errors
    } finally {
      clearAuth()
    }
  }

  async function fetchUser() {
    try {
      const profile = await authApi.me()
      user.value = profile
    } catch (e: unknown) {
      if (e instanceof UnauthorizedError) {
        clearAuth()
      }
      throw e
    }
  }

  async function restoreSession() {
    const savedToken = getStorage().getItem(TOKEN_KEY)
    if (!savedToken) return false
    token.value = savedToken
    try {
      await fetchUser()
      return true
    } catch {
      clearAuth()
      return false
    }
  }

  return {
    user,
    token,
    loading,
    error,
    isAuthenticated,
    userRole,
    login,
    register,
    telegramAuth,
    logout,
    fetchUser,
    restoreSession,
  }
})
