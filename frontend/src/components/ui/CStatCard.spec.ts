// The Stat tile (K46) as the cabinet draws it: a plain tile, the link form by `to`,
// the button form by @click, and the pending figure.

import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createI18n } from 'vue-i18n'
import CStatCard from './CStatCard.vue'

async function mountCard(
  props: { label: string } & Record<string, unknown>,
  attrs: Record<string, unknown> = {},
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()
  const i18n = createI18n({
    legacy: false,
    locale: 'en',
    messages: { en: { common: { stat: { loading: 'Loading {label}' } } } },
  })
  const w = mount(CStatCard, { props, attrs, global: { plugins: [router, i18n] } })
  await flushPromises()
  return w
}

describe('CStatCard', () => {
  it('draws a plain tile out of the tab order', async () => {
    const w = await mountCard({ label: 'Balance', value: '10.00' })
    expect(w.find('.ds-stat__label').text()).toBe('Balance')
    expect(w.find('.ds-stat__value').text()).toBe('10.00')
    expect(w.classes()).not.toContain('ds-stat--interactive')
    expect(w.find('.ds-stat__link').exists()).toBe(false)
  })

  it('draws the link form for `to`: one anchor in the label, to that address', async () => {
    const w = await mountCard({ label: 'Balance', value: '10.00', to: '/company/balance' })
    expect(w.classes()).toContain('ds-stat--interactive')
    const links = w.findAll('.ds-stat__label a.ds-stat__link')
    expect(links).toHaveLength(1)
    expect(links[0]?.attributes('href')).toBe('/company/balance')
    expect(links[0]?.text()).toBe('Balance')
    expect(w.find('button').exists()).toBe(false)
  })

  it('keeps the button form for a listener', async () => {
    const onClick = vi.fn()
    const w = await mountCard({ label: 'Open', value: '7' }, { onClick })
    await w.find('button.ds-stat__link').trigger('click')
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(w.find('a').exists()).toBe(false)
  })

  it('draws the pending figure: aria-busy, a skeleton bar, one status text naming the label', async () => {
    const w = await mountCard({ label: 'Balance', pending: true, change: '+1%' })
    expect(w.attributes('aria-busy')).toBe('true')
    const value = w.find('.ds-stat__value')
    expect(value.find('.ds-skeleton.ds-stat__pending[aria-hidden="true"]').exists()).toBe(true)
    expect(value.find('.ds-sr-only[role="status"]').text()).toBe('Loading Balance')
    expect(w.find('.ds-stat__change').exists()).toBe(false)
    await w.setProps({ pending: false, value: '5.00' })
    expect(w.attributes('aria-busy')).toBeUndefined()
    expect(w.find('.ds-stat__value').text()).toBe('5.00')
    expect(w.find('.ds-stat__pending').exists()).toBe(false)
  })
})
