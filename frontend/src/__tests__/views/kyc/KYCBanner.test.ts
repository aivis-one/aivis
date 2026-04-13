import { describe, it, expect, vi } from 'vitest'
import KYCBanner from '@/components/shared/KYCBanner.vue'
import { mountWithI18n } from '../../helpers'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/' }),
}))

describe('KYCBanner', () => {
  it('renders start CTA when status is none', () => {
    const wrapper = mountWithI18n(KYCBanner, {
      props: { status: 'none' },
    })
    expect(wrapper.find('.kyc-banner--none').exists()).toBe(true)
    expect(wrapper.find('.c-btn--primary').exists()).toBe(true)
  })

  it('renders review message when status is pending', () => {
    const wrapper = mountWithI18n(KYCBanner, {
      props: { status: 'pending' },
    })
    expect(wrapper.find('.kyc-banner--pending').exists()).toBe(true)
    expect(wrapper.find('.kyc-banner__link').exists()).toBe(true)
  })

  it('renders success when status is approved', () => {
    const wrapper = mountWithI18n(KYCBanner, {
      props: { status: 'approved' },
    })
    expect(wrapper.find('.kyc-banner--approved').exists()).toBe(true)
  })

  it('renders rejection reason when status is rejected', () => {
    const wrapper = mountWithI18n(KYCBanner, {
      props: { status: 'rejected', rejectionReason: 'Blurry photo' },
    })
    expect(wrapper.find('.kyc-banner--rejected').exists()).toBe(true)
    expect(wrapper.find('.kyc-banner__reason').text()).toBe('Blurry photo')
  })

  it('emits start on CTA click', async () => {
    const wrapper = mountWithI18n(KYCBanner, {
      props: { status: 'none' },
    })
    await wrapper.find('.c-btn--primary').trigger('click')
    expect(wrapper.emitted('start')).toBeTruthy()
  })

  it('emits resume on resubmit click', async () => {
    const wrapper = mountWithI18n(KYCBanner, {
      props: { status: 'rejected' },
    })
    await wrapper.find('.c-btn--secondary').trigger('click')
    expect(wrapper.emitted('resume')).toBeTruthy()
  })
})
