import { describe, it, expect, vi } from 'vitest'
import CNetworkError from '@/components/shared/CNetworkError.vue'
import { mountWithI18n } from '../../helpers'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/' }),
}))

describe('CNetworkError', () => {
  it('renders default message', () => {
    const wrapper = mountWithI18n(CNetworkError)
    expect(wrapper.find('.c-network-error__message').exists()).toBe(true)
  })

  it('renders custom message', () => {
    const wrapper = mountWithI18n(CNetworkError, {
      props: { message: 'Custom error text' },
    })
    expect(wrapper.find('.c-network-error__message').text()).toBe('Custom error text')
  })

  it('shows retry button when retryable', () => {
    const wrapper = mountWithI18n(CNetworkError, {
      props: { retryable: true },
    })
    expect(wrapper.find('.c-btn--secondary').exists()).toBe(true)
  })

  it('hides retry button when not retryable', () => {
    const wrapper = mountWithI18n(CNetworkError, {
      props: { retryable: false },
    })
    expect(wrapper.find('.c-btn--secondary').exists()).toBe(false)
  })

  it('emits retry on button click', async () => {
    const wrapper = mountWithI18n(CNetworkError, {
      props: { retryable: true },
    })
    await wrapper.find('.c-btn--secondary').trigger('click')
    expect(wrapper.emitted('retry')).toBeTruthy()
  })
})
