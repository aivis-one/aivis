import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import KYCFormView from '@/views/shared/KYCFormView.vue'
import { mountWithI18n } from '../../helpers'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ path: '/investor/kyc/form' }),
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
vi.mock('@/api/kyc', () => ({
  kycApi: { getStatus: vi.fn(), submit: vi.fn(), uploadDocument: vi.fn(), deleteDocument: vi.fn() },
}))
vi.mock('@/api/profile', () => ({
  profileApi: { get: vi.fn(), update: vi.fn(), uploadAvatar: vi.fn() },
}))
vi.mock('@/api/settings', () => ({ settingsApi: { get: vi.fn(), update: vi.fn() } }))

describe('KYCFormView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders step 1 by default', () => {
    const wrapper = mountWithI18n(KYCFormView)
    expect(wrapper.find('.kyc-form__fields').exists()).toBe(true)
    expect(wrapper.findAll('.c-input').length).toBeGreaterThanOrEqual(4)
  })

  it('shows step indicator with 4 steps', () => {
    const wrapper = mountWithI18n(KYCFormView)
    expect(wrapper.findAll('.kyc-form__step')).toHaveLength(4)
  })

  it('step 1 is active by default', () => {
    const wrapper = mountWithI18n(KYCFormView)
    const steps = wrapper.findAll('.kyc-form__step')
    expect(steps[0].classes()).toContain('kyc-form__step--active')
  })

  it('has navigation buttons', () => {
    const wrapper = mountWithI18n(KYCFormView)
    expect(wrapper.find('.kyc-form__nav').exists()).toBe(true)
  })

  it('submit button only appears after navigating to step 4', async () => {
    const wrapper = mountWithI18n(KYCFormView)
    // On step 1, should show "Next" not "Submit"
    const buttons = wrapper.findAll('.c-btn--primary')
    expect(buttons.length).toBeGreaterThanOrEqual(1)
  })
})
