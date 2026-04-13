import { describe, it, expect, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import CToast from '@/components/ui/CToast.vue'
import { useToast } from '@/composables/useToast'
import { mountWithI18n } from '../../helpers'

describe('CToast', () => {
  beforeEach(() => {
    const { clearAll } = useToast()
    clearAll()
  })

  it('renders nothing when no toasts', () => {
    const wrapper = mountWithI18n(CToast)
    expect(wrapper.findAll('.c-toast')).toHaveLength(0)
  })

  it('renders toast when addToast called', async () => {
    const wrapper = mountWithI18n(CToast)
    const { addToast } = useToast()
    addToast('success', 'Saved!')
    await nextTick()
    expect(wrapper.findAll('.c-toast')).toHaveLength(1)
    expect(wrapper.find('.c-toast__message').text()).toBe('Saved!')
  })

  it('shows correct type class', async () => {
    const wrapper = mountWithI18n(CToast)
    const { addToast } = useToast()

    addToast('error', 'Error msg', 0)
    await nextTick()
    expect(wrapper.find('.c-toast--error').exists()).toBe(true)

    addToast('warning', 'Warning msg', 0)
    await nextTick()
    expect(wrapper.find('.c-toast--warning').exists()).toBe(true)

    addToast('info', 'Info msg', 0)
    await nextTick()
    expect(wrapper.find('.c-toast--info').exists()).toBe(true)
  })

  it('close button removes toast', async () => {
    const wrapper = mountWithI18n(CToast)
    const { addToast } = useToast()
    addToast('success', 'Will close', 0)
    await nextTick()
    expect(wrapper.findAll('.c-toast')).toHaveLength(1)
    await wrapper.find('.c-toast__close').trigger('click')
    await nextTick()
    expect(wrapper.findAll('.c-toast')).toHaveLength(0)
  })
})
