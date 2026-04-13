import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import SettingsView from '@/views/shared/SettingsView.vue'
import { mountWithI18n } from '../../helpers'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/investor/settings' }),
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
  profileApi: { get: vi.fn(), update: vi.fn(), uploadAvatar: vi.fn() },
}))

const mockSettingsApi = vi.hoisted(() => ({
  get: vi.fn().mockResolvedValue({
    theme: 'system',
    language: 'en',
    notifications_email: true,
    notifications_push: true,
    notifications_sms: false,
  }),
  update: vi.fn().mockResolvedValue({
    theme: 'dark',
    language: 'en',
    notifications_email: true,
    notifications_push: true,
    notifications_sms: false,
  }),
}))

vi.mock('@/api/settings', () => ({ settingsApi: mockSettingsApi }))

describe('SettingsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockSettingsApi.get.mockResolvedValue({
      theme: 'system',
      language: 'en',
      notifications_email: true,
      notifications_push: true,
      notifications_sms: false,
    })
    mockSettingsApi.update.mockResolvedValue({
      theme: 'dark',
      language: 'en',
      notifications_email: true,
      notifications_push: true,
      notifications_sms: false,
    })
  })

  it('renders settings sections', async () => {
    const wrapper = mountWithI18n(SettingsView)
    await nextTick()
    const sections = wrapper.findAll('.settings-view__section')
    expect(sections.length).toBe(3)
  })

  it('renders theme options', async () => {
    const wrapper = mountWithI18n(SettingsView)
    await nextTick()
    const options = wrapper.findAll('.settings-view__option')
    expect(options.length).toBe(3)
  })

  it('renders notification toggles', async () => {
    const wrapper = mountWithI18n(SettingsView)
    await nextTick()
    const toggles = wrapper.findAll('.settings-view__toggle')
    expect(toggles.length).toBe(3)
  })

  it('theme button click changes active class', async () => {
    const wrapper = mountWithI18n(SettingsView)
    await nextTick()
    await wrapper.findAll('.settings-view__option')[1].trigger('click')
    await nextTick()
    // Re-query after reactive update
    const activeBtn = wrapper.find('.settings-view__option--active')
    expect(activeBtn.exists()).toBe(true)
  })

  it('renders language selector', async () => {
    const wrapper = mountWithI18n(SettingsView)
    await nextTick()
    expect(wrapper.find('.settings-view__select').exists()).toBe(true)
  })
})
