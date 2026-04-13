import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useProfileStore } from '@/stores/profile'
import { useAuthStore } from '@/stores/auth'
import type { ProfileData, UserSettings } from '@/api/types'

const mockProfileApi = vi.hoisted(() => ({
  get: vi.fn(),
  update: vi.fn(),
  uploadAvatar: vi.fn(),
}))

const mockSettingsApi = vi.hoisted(() => ({
  get: vi.fn(),
  update: vi.fn(),
}))

vi.mock('@/api/profile', () => ({ profileApi: mockProfileApi }))
vi.mock('@/api/settings', () => ({ settingsApi: mockSettingsApi }))
vi.mock('@/platform', () => ({ platform: { type: 'standalone' } }))
vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    telegramAuth: vi.fn(),
    logout: vi.fn(),
    me: vi.fn(),
  },
}))

function makeProfile(overrides: Partial<ProfileData> = {}): ProfileData {
  return {
    first_name: 'John',
    last_name: 'Doe',
    phone: '+1234567890',
    avatar_url: null,
    bio: 'Test bio',
    country: 'US',
    city: 'New York',
    language: 'en',
    timezone: 'America/New_York',
    ...overrides,
  }
}

function makeSettings(overrides: Partial<UserSettings> = {}): UserSettings {
  return {
    theme: 'system',
    language: 'en',
    notifications_email: true,
    notifications_push: true,
    notifications_sms: false,
    ...overrides,
  }
}

describe('profile store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
  })

  describe('fetchProfile', () => {
    it('sets profile state on success', async () => {
      const profile = makeProfile()
      mockProfileApi.get.mockResolvedValue(profile)

      const store = useProfileStore()
      await store.fetchProfile()

      expect(store.profile).toEqual(profile)
      expect(store.loading).toBe(false)
      expect(store.error).toBeNull()
    })

    it('sets error on failure', async () => {
      mockProfileApi.get.mockRejectedValue(new Error('Network error'))

      const store = useProfileStore()
      await expect(store.fetchProfile()).rejects.toThrow('Network error')

      expect(store.error).toBe('Network error')
      expect(store.loading).toBe(false)
    })
  })

  describe('updateProfile', () => {
    it('updates profile and returns true on success', async () => {
      const updated = makeProfile({ first_name: 'Jane' })
      mockProfileApi.update.mockResolvedValue(updated)

      const store = useProfileStore()
      const result = await store.updateProfile({ first_name: 'Jane' })

      expect(result).toBe(true)
      expect(store.profile?.first_name).toBe('Jane')
    })

    it('updates auth store user profile on success', async () => {
      const updated = makeProfile({ first_name: 'Jane' })
      mockProfileApi.update.mockResolvedValue(updated)

      const authStore = useAuthStore()
      authStore.user = {
        id: '1',
        role: 'investor',
        is_active: true,
        onboarding_step: 'role_selected',
        kyc_status: 'none',
        profile: makeProfile(),
        language: 'en',
        created_at: '',
        updated_at: '',
      }

      const store = useProfileStore()
      await store.updateProfile({ first_name: 'Jane' })

      expect(authStore.user.profile.first_name).toBe('Jane')
    })

    it('returns false and sets error on failure', async () => {
      mockProfileApi.update.mockRejectedValue(new Error('Update failed'))

      const store = useProfileStore()
      const result = await store.updateProfile({ first_name: 'Jane' })

      expect(result).toBe(false)
      expect(store.error).toBe('Update failed')
    })
  })

  describe('uploadAvatar', () => {
    it('updates avatar_url on success', async () => {
      mockProfileApi.uploadAvatar.mockResolvedValue({ avatar_url: 'https://cdn/avatar.jpg' })

      const store = useProfileStore()
      store.profile = makeProfile()
      const result = await store.uploadAvatar(new File([''], 'avatar.jpg'))

      expect(result).toBe(true)
      expect(store.profile?.avatar_url).toBe('https://cdn/avatar.jpg')
    })

    it('returns false on failure', async () => {
      mockProfileApi.uploadAvatar.mockRejectedValue(new Error('Upload failed'))

      const store = useProfileStore()
      const result = await store.uploadAvatar(new File([''], 'avatar.jpg'))

      expect(result).toBe(false)
      expect(store.error).toBe('Upload failed')
    })
  })

  describe('fetchSettings', () => {
    it('sets settings state on success', async () => {
      const settings = makeSettings()
      mockSettingsApi.get.mockResolvedValue(settings)

      const store = useProfileStore()
      await store.fetchSettings()

      expect(store.settings).toEqual(settings)
    })
  })

  describe('updateSettings', () => {
    it('updates settings and returns true', async () => {
      const updated = makeSettings({ theme: 'dark' })
      mockSettingsApi.update.mockResolvedValue(updated)

      const store = useProfileStore()
      const result = await store.updateSettings({ theme: 'dark' })

      expect(result).toBe(true)
      expect(store.settings?.theme).toBe('dark')
    })
  })

  describe('getters', () => {
    it('fullName joins first and last name', () => {
      const store = useProfileStore()
      store.profile = makeProfile({ first_name: 'John', last_name: 'Doe' })
      expect(store.fullName).toBe('John Doe')
    })

    it('fullName handles missing last name', () => {
      const store = useProfileStore()
      store.profile = makeProfile({ first_name: 'John', last_name: '' })
      expect(store.fullName).toBe('John')
    })

    it('hasAvatar returns true when avatar_url is set', () => {
      const store = useProfileStore()
      store.profile = makeProfile({ avatar_url: 'https://cdn/avatar.jpg' })
      expect(store.hasAvatar).toBe(true)
    })

    it('hasAvatar returns false when avatar_url is null', () => {
      const store = useProfileStore()
      store.profile = makeProfile({ avatar_url: null })
      expect(store.hasAvatar).toBe(false)
    })
  })
})
