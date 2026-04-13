import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import KYCUploadView from '@/views/shared/KYCUploadView.vue'
import { mountWithI18n } from '../../helpers'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/investor/kyc/upload' }),
}))

vi.mock('@/api/kyc', () => ({
  kycApi: { getStatus: vi.fn(), submit: vi.fn(), uploadDocument: vi.fn(), deleteDocument: vi.fn() },
}))

describe('KYCUploadView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders document type selector', () => {
    const wrapper = mountWithI18n(KYCUploadView)
    expect(wrapper.find('.kyc-upload__select').exists()).toBe(true)
  })

  it('renders CFileUpload component', () => {
    const wrapper = mountWithI18n(KYCUploadView)
    expect(wrapper.find('.c-file-upload').exists()).toBe(true)
  })

  it('renders hint text', () => {
    const wrapper = mountWithI18n(KYCUploadView)
    expect(wrapper.find('.kyc-upload__hint').exists()).toBe(true)
  })

  it('shows navigation buttons when embedded', () => {
    const wrapper = mountWithI18n(KYCUploadView, {
      props: { embedded: true },
    })
    expect(wrapper.find('.kyc-upload__actions').exists()).toBe(true)
  })
})
