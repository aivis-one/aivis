import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useOnboardingStore } from '@/stores/onboarding'
import { useAuthStore } from '@/stores/auth'
import { useProfileStore } from '@/stores/profile'

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
vi.mock('@/api/profile', () => ({
  profileApi: { get: vi.fn(), update: vi.fn(), uploadAvatar: vi.fn() },
}))
vi.mock('@/api/settings', () => ({ settingsApi: { get: vi.fn(), update: vi.fn() } }))
vi.mock('@/api/kyc', () => ({
  kycApi: { getStatus: vi.fn(), submit: vi.fn(), uploadDocument: vi.fn(), deleteDocument: vi.fn() },
}))
vi.mock('@/api/documents', () => ({ documentsApi: { list: vi.fn(), get: vi.fn(), sign: vi.fn() } }))

describe('onboarding store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('returns 4 steps for investor', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: '1',
      role: 'investor',
      is_active: true,
      onboarding_step: '',
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
        timezone: '',
      },
      language: 'en',
      created_at: '',
      updated_at: '',
    }

    const store = useOnboardingStore()
    expect(store.steps).toHaveLength(4)
  })

  it('returns 2 steps for staff', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: '1',
      role: 'staff',
      is_active: true,
      onboarding_step: '',
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
        timezone: '',
      },
      language: 'en',
      created_at: '',
      updated_at: '',
    }

    const store = useOnboardingStore()
    expect(store.steps).toHaveLength(2)
  })

  it('isComplete false when profile not filled', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: '1',
      role: 'staff',
      is_active: true,
      onboarding_step: '',
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
        timezone: '',
      },
      language: 'en',
      created_at: '',
      updated_at: '',
    }

    const store = useOnboardingStore()
    expect(store.isComplete).toBe(false)
  })

  it('isComplete true when all staff steps done', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: '1',
      role: 'staff',
      is_active: true,
      onboarding_step: '',
      kyc_status: 'none',
      profile: {
        first_name: 'John',
        last_name: 'Doe',
        phone: '',
        avatar_url: null,
        bio: '',
        country: '',
        city: '',
        language: 'en',
        timezone: '',
      },
      language: 'en',
      created_at: '',
      updated_at: '',
    }

    const profileStore = useProfileStore()
    profileStore.profile = {
      first_name: 'John',
      last_name: 'Doe',
      phone: '',
      avatar_url: null,
      bio: '',
      country: '',
      city: '',
      language: 'en',
      timezone: '',
    }

    const store = useOnboardingStore()
    expect(store.isComplete).toBe(true)
  })

  it('currentStepIndex points to first incomplete', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: '1',
      role: 'investor',
      is_active: true,
      onboarding_step: '',
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
        timezone: '',
      },
      language: 'en',
      created_at: '',
      updated_at: '',
    }

    const store = useOnboardingStore()
    expect(store.currentStepIndex).toBe(0)
  })

  it('progress is 0 when nothing done', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: '1',
      role: 'investor',
      is_active: true,
      onboarding_step: '',
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
        timezone: '',
      },
      language: 'en',
      created_at: '',
      updated_at: '',
    }

    const store = useOnboardingStore()
    expect(store.progress).toBe(0)
  })

  it('progress is 33 when 1 of 3 steps done (investor)', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: '1',
      role: 'investor',
      is_active: true,
      onboarding_step: '',
      kyc_status: 'none',
      profile: {
        first_name: 'John',
        last_name: 'Doe',
        phone: '',
        avatar_url: null,
        bio: '',
        country: '',
        city: '',
        language: 'en',
        timezone: '',
      },
      language: 'en',
      created_at: '',
      updated_at: '',
    }

    const profileStore = useProfileStore()
    profileStore.profile = {
      first_name: 'John',
      last_name: 'Doe',
      phone: '',
      avatar_url: null,
      bio: '',
      country: '',
      city: '',
      language: 'en',
      timezone: '',
    }

    const store = useOnboardingStore()
    expect(store.progress).toBe(33)
  })
})
