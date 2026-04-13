import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import type { AuthResponse, UserResponse } from '@/api/types'
import { UnauthorizedError } from '@/api/types'

// Hoisted mocks — vi.mock factories are hoisted above imports
const mockAuthApi = vi.hoisted(() => ({
  login: vi.fn(),
  register: vi.fn(),
  telegramAuth: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
}))

vi.mock('@/platform', () => ({
  platform: { type: 'standalone' },
}))

vi.mock('@/api/auth', () => ({
  authApi: mockAuthApi,
}))

function makeUser(overrides: Partial<UserResponse> = {}): UserResponse {
  return {
    id: 'user-1',
    role: 'investor',
    is_active: true,
    onboarding_step: 'role_selected',
    kyc_status: 'none',
    profile: {
      first_name: '',
      last_name: '',
      phone: '',
      avatar_url: null,
      bio: '',
      country: '',
      city: '',
      language: 'en',
      timezone: 'UTC',
    },
    language: 'en',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function makeAuthResponse(overrides: Partial<AuthResponse> = {}): AuthResponse {
  return {
    user: makeUser(),
    session_token: 'test-token-123',
    ...overrides,
  }
}

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
  })

  describe('initial state', () => {
    it('has null user and token', () => {
      const store = useAuthStore()
      expect(store.user).toBeNull()
      expect(store.token).toBeNull()
      expect(store.loading).toBe(false)
      expect(store.error).toBeNull()
    })

    it('isAuthenticated is false', () => {
      const store = useAuthStore()
      expect(store.isAuthenticated).toBe(false)
    })

    it('userRole is null', () => {
      const store = useAuthStore()
      expect(store.userRole).toBeNull()
    })
  })

  describe('login', () => {
    it('sets token and user on success', async () => {
      const response = makeAuthResponse()
      mockAuthApi.login.mockResolvedValue(response)

      const store = useAuthStore()
      await store.login('test@example.com', 'password123')

      expect(store.token).toBe('test-token-123')
      expect(store.user).toEqual(response.user)
      expect(store.isAuthenticated).toBe(true)
      expect(store.userRole).toBe('investor')
      expect(store.loading).toBe(false)
      expect(store.error).toBeNull()
    })

    it('persists token to localStorage for standalone', async () => {
      mockAuthApi.login.mockResolvedValue(makeAuthResponse())

      const store = useAuthStore()
      await store.login('test@example.com', 'password123')

      expect(localStorage.getItem('auth_token')).toBe('test-token-123')
    })

    it('sets error and re-throws on API error', async () => {
      const apiError = new Error('Invalid credentials')
      mockAuthApi.login.mockRejectedValue(apiError)

      const store = useAuthStore()
      await expect(store.login('test@example.com', 'wrong')).rejects.toThrow('Invalid credentials')

      expect(store.error).toBe('Invalid credentials')
      expect(store.token).toBeNull()
      expect(store.user).toBeNull()
      expect(store.loading).toBe(false)
    })

    it('sets loading during request', async () => {
      let resolveLogin: (v: AuthResponse) => void
      mockAuthApi.login.mockReturnValue(
        new Promise<AuthResponse>((r) => {
          resolveLogin = r
        }),
      )

      const store = useAuthStore()
      const promise = store.login('test@example.com', 'password123')

      expect(store.loading).toBe(true)
      resolveLogin!(makeAuthResponse())
      await promise
      expect(store.loading).toBe(false)
    })
  })

  describe('register', () => {
    it('sets token and user on success', async () => {
      const response = makeAuthResponse({ session_token: 'reg-token' })
      mockAuthApi.register.mockResolvedValue(response)

      const store = useAuthStore()
      await store.register('new@example.com', 'password123')

      expect(store.token).toBe('reg-token')
      expect(store.user).toEqual(response.user)
      expect(store.isAuthenticated).toBe(true)
    })

    it('sets error on validation failure', async () => {
      mockAuthApi.register.mockRejectedValue(new Error('Email taken'))

      const store = useAuthStore()
      await expect(store.register('taken@example.com', 'pass')).rejects.toThrow('Email taken')

      expect(store.error).toBe('Email taken')
    })
  })

  describe('telegramAuth', () => {
    it('authenticates with Telegram initData', async () => {
      // Set up Telegram WebApp mock
      const originalTelegram = window.Telegram
      window.Telegram = { WebApp: { initData: 'mock-init-data' } } as never

      const response = makeAuthResponse({ session_token: 'tg-token' })
      mockAuthApi.telegramAuth.mockResolvedValue(response)

      const store = useAuthStore()
      await store.telegramAuth()

      expect(mockAuthApi.telegramAuth).toHaveBeenCalledWith({
        init_data: 'mock-init-data',
      })
      expect(store.token).toBe('tg-token')
      expect(store.isAuthenticated).toBe(true)

      window.Telegram = originalTelegram
    })

    it('throws when Telegram WebApp not available', async () => {
      const originalTelegram = window.Telegram
      window.Telegram = undefined as never

      const store = useAuthStore()
      await expect(store.telegramAuth()).rejects.toThrow('Telegram WebApp not available')

      window.Telegram = originalTelegram
    })
  })

  describe('logout', () => {
    it('clears state and storage', async () => {
      // Set up authenticated state
      mockAuthApi.login.mockResolvedValue(makeAuthResponse())
      const store = useAuthStore()
      await store.login('test@example.com', 'pass')

      expect(store.isAuthenticated).toBe(true)

      mockAuthApi.logout.mockResolvedValue(undefined)
      await store.logout()

      expect(store.user).toBeNull()
      expect(store.token).toBeNull()
      expect(store.isAuthenticated).toBe(false)
      expect(localStorage.getItem('auth_token')).toBeNull()
      expect(sessionStorage.getItem('auth_token')).toBeNull()
    })

    it('clears state even if API call fails', async () => {
      mockAuthApi.login.mockResolvedValue(makeAuthResponse())
      const store = useAuthStore()
      await store.login('test@example.com', 'pass')

      mockAuthApi.logout.mockRejectedValue(new Error('Network error'))
      await store.logout()

      expect(store.user).toBeNull()
      expect(store.token).toBeNull()
      expect(store.isAuthenticated).toBe(false)
    })
  })

  describe('fetchUser', () => {
    it('updates user on success', async () => {
      const user = makeUser({ role: 'agent' })
      mockAuthApi.me.mockResolvedValue(user)

      const store = useAuthStore()
      await store.fetchUser()

      expect(store.user).toEqual(user)
      expect(store.userRole).toBe('agent')
    })

    it('clears auth on UnauthorizedError', async () => {
      mockAuthApi.login.mockResolvedValue(makeAuthResponse())
      const store = useAuthStore()
      await store.login('test@example.com', 'pass')

      mockAuthApi.me.mockRejectedValue(new UnauthorizedError())
      await expect(store.fetchUser()).rejects.toThrow()

      expect(store.user).toBeNull()
      expect(store.token).toBeNull()
    })

    it('does not clear auth on other errors', async () => {
      mockAuthApi.login.mockResolvedValue(makeAuthResponse())
      const store = useAuthStore()
      await store.login('test@example.com', 'pass')

      mockAuthApi.me.mockRejectedValue(new Error('Network error'))
      await expect(store.fetchUser()).rejects.toThrow('Network error')

      // Token should still be set (not cleared for non-401 errors)
      expect(store.token).toBe('test-token-123')
    })
  })

  describe('restoreSession', () => {
    it('restores from localStorage token', async () => {
      localStorage.setItem('auth_token', 'saved-token')
      const user = makeUser()
      mockAuthApi.me.mockResolvedValue(user)

      const store = useAuthStore()
      const result = await store.restoreSession()

      expect(result).toBe(true)
      expect(store.token).toBe('saved-token')
      expect(store.user).toEqual(user)
    })

    it('returns false when no saved token', async () => {
      const store = useAuthStore()
      const result = await store.restoreSession()

      expect(result).toBe(false)
      expect(store.token).toBeNull()
    })

    it('clears auth if fetchUser fails during restore', async () => {
      localStorage.setItem('auth_token', 'expired-token')
      mockAuthApi.me.mockRejectedValue(new UnauthorizedError())

      const store = useAuthStore()
      const result = await store.restoreSession()

      expect(result).toBe(false)
      expect(store.token).toBeNull()
      expect(store.user).toBeNull()
    })
  })

  describe('platform storage', () => {
    it('uses sessionStorage for telegram platform', async () => {
      // Override platform mock for this test
      const platformModule = await import('@/platform')
      const original = platformModule.platform.type
      Object.defineProperty(platformModule.platform, 'type', {
        value: 'telegram',
        writable: true,
      })

      mockAuthApi.login.mockResolvedValue(makeAuthResponse())
      const store = useAuthStore()
      await store.login('test@example.com', 'pass')

      expect(sessionStorage.getItem('auth_token')).toBe('test-token-123')
      expect(localStorage.getItem('auth_token')).toBeNull()

      // Restore
      Object.defineProperty(platformModule.platform, 'type', {
        value: original,
        writable: true,
      })
    })
  })
})
