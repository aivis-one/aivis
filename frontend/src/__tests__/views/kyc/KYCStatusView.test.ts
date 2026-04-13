import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import KYCStatusView from '@/views/shared/KYCStatusView.vue'
import { mountWithI18n } from '../../helpers'

const mockPush = vi.fn()
const mockReplace = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  useRoute: () => ({ path: '/investor/kyc' }),
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

const mockKycApi = vi.hoisted(() => ({
  getStatus: vi.fn().mockResolvedValue({
    status: 'pending',
    submission: {
      id: 'sub-1',
      status: 'pending',
      submitted_at: '2026-04-12',
      documents: [],
      personal_data: {
        full_name: 'John',
        date_of_birth: '1990-01-01',
        nationality: 'US',
        address: '123 St',
        tax_id: '',
      },
    },
  }),
  submit: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
}))

vi.mock('@/api/kyc', () => ({ kycApi: mockKycApi }))
vi.mock('@/api/profile', () => ({
  profileApi: { get: vi.fn(), update: vi.fn(), uploadAvatar: vi.fn() },
}))
vi.mock('@/api/settings', () => ({ settingsApi: { get: vi.fn(), update: vi.fn() } }))

describe('KYCStatusView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockKycApi.getStatus.mockResolvedValue({
      status: 'pending',
      submission: {
        id: 'sub-1',
        status: 'pending',
        submitted_at: '2026-04-12',
        documents: [],
        personal_data: {
          full_name: 'John',
          date_of_birth: '1990-01-01',
          nationality: 'US',
          address: '123 St',
          tax_id: '',
        },
      },
    })
  })

  it('renders title', async () => {
    const wrapper = mountWithI18n(KYCStatusView)
    await nextTick()
    await nextTick()
    expect(wrapper.find('.kyc-status__title').exists()).toBe(true)
  })

  it('renders timeline when submission exists', async () => {
    const wrapper = mountWithI18n(KYCStatusView)
    await nextTick()
    await nextTick()
    expect(wrapper.findAll('.kyc-status__timeline-item').length).toBeGreaterThanOrEqual(1)
  })

  it('renders rejection details when rejected', async () => {
    mockKycApi.getStatus.mockResolvedValue({
      status: 'rejected',
      submission: {
        id: 'sub-1',
        status: 'rejected',
        submitted_at: '2026-04-12',
        reviewed_at: '2026-04-12',
        rejection_reason: 'Blurry image',
        documents: [],
        personal_data: {
          full_name: 'John',
          date_of_birth: '1990-01-01',
          nationality: 'US',
          address: '123 St',
          tax_id: '',
        },
      },
    })

    const wrapper = mountWithI18n(KYCStatusView)
    await nextTick()
    await nextTick()
    expect(wrapper.find('.kyc-status__rejection').exists()).toBe(true)
    expect(wrapper.find('.kyc-status__rejection-text').text()).toBe('Blurry image')
  })

  it('resubmit button navigates to form', async () => {
    mockKycApi.getStatus.mockResolvedValue({
      status: 'rejected',
      submission: {
        id: 'sub-1',
        status: 'rejected',
        submitted_at: '2026-04-12',
        reviewed_at: '2026-04-12',
        rejection_reason: 'Blurry',
        documents: [],
        personal_data: {
          full_name: 'John',
          date_of_birth: '1990-01-01',
          nationality: 'US',
          address: '123 St',
          tax_id: '',
        },
      },
    })

    const wrapper = mountWithI18n(KYCStatusView)
    await nextTick()
    await nextTick()
    await wrapper.find('.c-btn--primary').trigger('click')
    expect(mockPush).toHaveBeenCalledWith('/investor/kyc/form')
  })
})
