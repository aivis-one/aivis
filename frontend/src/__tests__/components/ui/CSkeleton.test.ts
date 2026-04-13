import { describe, it, expect } from 'vitest'
import CSkeleton from '@/components/ui/CSkeleton.vue'
import { mountWithI18n } from '../../helpers'

describe('CSkeleton', () => {
  it('renders text variant with default 3 lines', () => {
    const wrapper = mountWithI18n(CSkeleton)
    expect(wrapper.findAll('.c-skeleton__line')).toHaveLength(3)
  })

  it('renders text variant with custom line count', () => {
    const wrapper = mountWithI18n(CSkeleton, {
      props: { variant: 'text', lines: 5 },
    })
    expect(wrapper.findAll('.c-skeleton__line')).toHaveLength(5)
  })

  it('renders card variant', () => {
    const wrapper = mountWithI18n(CSkeleton, {
      props: { variant: 'card' },
    })
    expect(wrapper.find('.c-skeleton--card').exists()).toBe(true)
    // Header line + 3 body lines = 4
    expect(wrapper.findAll('.c-skeleton__line')).toHaveLength(4)
  })

  it('renders list variant', () => {
    const wrapper = mountWithI18n(CSkeleton, {
      props: { variant: 'list' },
    })
    expect(wrapper.findAll('.c-skeleton__row')).toHaveLength(3)
    expect(wrapper.findAll('.c-skeleton__circle--sm')).toHaveLength(3)
  })

  it('renders avatar variant', () => {
    const wrapper = mountWithI18n(CSkeleton, {
      props: { variant: 'avatar' },
    })
    expect(wrapper.find('.c-skeleton__circle').exists()).toBe(true)
  })

  it('applies custom width and height', () => {
    const wrapper = mountWithI18n(CSkeleton, {
      props: { variant: 'avatar', width: '200px', height: '64px' },
    })
    expect(wrapper.find('.c-skeleton').attributes('style')).toContain('width: 200px')
    expect(wrapper.find('.c-skeleton__circle').attributes('style')).toContain('height: 64px')
  })

  it('has shimmer animation class', () => {
    const wrapper = mountWithI18n(CSkeleton)
    expect(wrapper.find('.c-skeleton__shimmer').exists()).toBe(true)
  })
})
