import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ProfileEditView from '@/views/shared/ProfileEditView.vue'
import { mountWithI18n } from '../../helpers'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ path: '/investor/profile/edit' }),
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

const mockProfileApi = vi.hoisted(() => ({
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
}))

vi.mock('@/api/profile', () => ({ profileApi: mockProfileApi }))
vi.mock('@/api/settings', () => ({ settingsApi: { get: vi.fn(), update: vi.fn() } }))

describe('ProfileEditView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockProfileApi.get.mockResolvedValue({
      first_name: 'John',
      last_name: 'Doe',
      phone: '+1234567890',
      avatar_url: null,
      bio: 'Test bio',
      country: 'US',
      city: 'New York',
      language: 'en',
      timezone: 'America/New_York',
    })
  })

  it('renders form with inputs', async () => {
    const wrapper = mountWithI18n(ProfileEditView)
    await nextTick()
    await nextTick()
    const inputs = wrapper.findAll('.c-input__field')
    expect(inputs.length).toBeGreaterThanOrEqual(4)
  })

  it('has CFileUpload for avatar', async () => {
    const wrapper = mountWithI18n(ProfileEditView)
    await nextTick()
    expect(wrapper.find('.c-file-upload').exists()).toBe(true)
  })

  it('cancel navigates back', async () => {
    const wrapper = mountWithI18n(ProfileEditView)
    await nextTick()
    const ghostBtn = wrapper.find('.c-btn--ghost')
    await ghostBtn.trigger('click')
    expect(mockPush).toHaveBeenCalledWith('/investor/profile')
  })

  it('submit calls updateProfile', async () => {
    mockProfileApi.update.mockResolvedValue({
      first_name: 'John',
      last_name: 'Doe',
      phone: '+1234567890',
      avatar_url: null,
      bio: 'Test bio',
      country: 'US',
      city: 'New York',
      language: 'en',
      timezone: 'America/New_York',
    })

    const wrapper = mountWithI18n(ProfileEditView)
    await nextTick()
    await nextTick()

    await wrapper.find('form').trigger('submit')
    await nextTick()

    expect(mockProfileApi.update).toHaveBeenCalled()
  })
})
