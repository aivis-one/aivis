import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ProfileView from '@/views/shared/ProfileView.vue'
import { mountWithI18n } from '../../helpers'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ path: '/investor/profile' }),
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
      first_name: 'John',
      last_name: 'Doe',
      phone: '+1234567890',
      avatar_url: null,
      bio: 'Test bio',
      country: 'US',
      city: 'New York',
      language: 'en',
      timezone: 'America/New_York',
    }),
    update: vi.fn(),
    uploadAvatar: vi.fn(),
  },
}))
vi.mock('@/api/settings', () => ({ settingsApi: { get: vi.fn(), update: vi.fn() } }))

describe('ProfileView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders profile data when loaded', async () => {
    const wrapper = mountWithI18n(ProfileView)
    await nextTick()
    await nextTick()
    expect(wrapper.find('.profile-view__name').text()).toBe('John Doe')
  })

  it('shows edit button', async () => {
    const wrapper = mountWithI18n(ProfileView)
    await nextTick()
    await nextTick()
    const btn = wrapper.find('.c-btn--primary')
    expect(btn.exists()).toBe(true)
  })

  it('edit button navigates to edit route', async () => {
    const wrapper = mountWithI18n(ProfileView)
    await nextTick()
    await nextTick()
    await wrapper.find('.c-btn--primary').trigger('click')
    expect(mockPush).toHaveBeenCalledWith('/investor/profile/edit')
  })
})
