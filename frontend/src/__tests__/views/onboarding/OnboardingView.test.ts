import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import OnboardingView from '@/views/shared/OnboardingView.vue'
import { mountWithI18n } from '../../helpers'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ path: '/onboarding' }),
}))

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
  profileApi: {
    get: vi.fn().mockResolvedValue({
      first_name: '',
      last_name: '',
      phone: '',
      avatar_url: null,
      bio: '',
      country: '',
      city: '',
      language: 'en',
      timezone: '',
    }),
    update: vi.fn(),
    uploadAvatar: vi.fn(),
  },
}))
vi.mock('@/api/settings', () => ({ settingsApi: { get: vi.fn(), update: vi.fn() } }))
vi.mock('@/api/kyc', () => ({
  kycApi: {
    getStatus: vi.fn().mockResolvedValue({ status: 'none' }),
    submit: vi.fn(),
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
  },
}))
vi.mock('@/api/documents', () => ({
  documentsApi: {
    list: vi.fn().mockResolvedValue({ data: [], total: 0, page: 1, per_page: 10 }),
    get: vi.fn(),
    sign: vi.fn(),
  },
}))

describe('OnboardingView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders title', async () => {
    const wrapper = mountWithI18n(OnboardingView)
    await nextTick()
    expect(wrapper.find('.onboarding__title').exists()).toBe(true)
  })

  it('renders progress bar', async () => {
    const wrapper = mountWithI18n(OnboardingView)
    await nextTick()
    expect(wrapper.find('.onboarding__progress').exists()).toBe(true)
  })

  it('renders step cards', async () => {
    const wrapper = mountWithI18n(OnboardingView)
    await nextTick()
    await nextTick()
    const steps = wrapper.findAll('.onboarding__step')
    expect(steps.length).toBeGreaterThanOrEqual(2)
  })

  it('first step is active', async () => {
    const wrapper = mountWithI18n(OnboardingView)
    await nextTick()
    await nextTick()
    expect(wrapper.find('.onboarding__step--active').exists()).toBe(true)
  })
})
