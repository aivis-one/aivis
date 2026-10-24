// The Loader (K20): the bare spinner, and the centred block for a section or a page.

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import CLoader from './CLoader.vue'

function mountLoader(props: Record<string, unknown> = {}) {
  const i18n = createI18n({
    legacy: false,
    locale: 'en',
    messages: { en: { common: { loading: 'Loading...' } } },
  })
  return mount(CLoader, { props, global: { plugins: [i18n] } })
}

describe('CLoader', () => {
  it('keeps the bare form: a status span with the ring and a screen-reader word', () => {
    const w = mountLoader()
    expect(w.element.tagName).toBe('SPAN')
    expect(w.classes()).toEqual(['ds-loader'])
    expect(w.attributes('role')).toBe('status')
    expect(w.attributes('data-size')).toBeUndefined()
    expect(w.find('.ds-loader__ring').attributes('aria-hidden')).toBe('true')
    expect(w.find('.ds-sr-only').text()).toBe('Loading...')
    expect(mountLoader({ size: 20 }).attributes('data-size')).toBe('sm')
  })

  it('draws the centred block with a visible status text, and no page extent by default', () => {
    const w = mountLoader({ centered: true })
    expect(w.element.tagName).toBe('DIV')
    expect(w.classes()).toEqual(['ds-loader', 'ds-loader--centered'])
    expect(w.attributes('role')).toBe('status')
    expect(w.attributes('data-extent')).toBeUndefined()
    expect(w.find('.ds-loader__ring').exists()).toBe(true)
    expect(w.find('.ds-sr-only').exists()).toBe(false)
    expect(w.text()).toBe('Loading...')
  })

  it('gives the centred block a page extent when asked, and ignores extent on the bare form', () => {
    expect(mountLoader({ centered: true, extent: 'page' }).attributes('data-extent')).toBe('page')
    expect(mountLoader({ extent: 'page' }).attributes('data-extent')).toBeUndefined()
  })
})
