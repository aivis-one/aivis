// The frame's one menu: links, the current mark by path prefix, the mark of AIVIS.

import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppNav from './AppNav.vue'
import { extraTabsFor, INVESTOR_TABS } from '@/router/tabs'

async function mountAt(path: string, extra = false) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(AppNav, {
    props: { items: INVESTOR_TABS, extra: extra ? extraTabsFor('investor') : [] },
    global: { plugins: [router, createPinia()] },
  })
  await flushPromises()
  return w
}

describe('AppNav', () => {
  it('is one nav landmark holding a link for each item, with the mark of AIVIS ahead of them', async () => {
    const w = await mountAt('/investor/dashboard')
    expect(w.findAll('nav.ds-nav')).toHaveLength(1)
    expect(w.findAll('a.ds-navitem')).toHaveLength(INVESTOR_TABS.length)
    expect(w.find('li.ds-nav__brand a.ds-nav__logo img.ds-nav__mark').exists()).toBe(true)
    expect(w.findAll('a.ds-navitem').map((a) => a.attributes('href'))).toEqual(
      INVESTOR_TABS.map((t) => t.path),
    )
  })

  it('marks the item whose path the route is in, and only that one', async () => {
    const w = await mountAt('/investor/portfolio/company-7')
    const current = w.findAll('a.ds-navitem[aria-current="page"]')
    expect(current).toHaveLength(1)
    expect(current[0]?.attributes('href')).toBe('/investor/portfolio')
  })

  it('marks nothing on a screen no tab holds', async () => {
    const w = await mountAt('/investor/news')
    expect(w.findAll('a.ds-navitem[aria-current="page"]')).toHaveLength(0)
  })

  it('lists the other sections of the role before the last item, from the web width', async () => {
    const w = await mountAt('/investor/dashboard', true)
    const hrefs = w.findAll('a.ds-navitem').map((a) => a.attributes('href'))
    expect(hrefs).toEqual([
      ...INVESTOR_TABS.slice(0, -1).map((t) => t.path),
      ...extraTabsFor('investor').map((t) => t.path),
      INVESTOR_TABS[INVESTOR_TABS.length - 1]?.path,
    ])
    for (const section of ['news', 'docs', 'support', 'faq']) {
      expect(extraTabsFor('investor').map((t) => t.id)).toContain(section)
    }
    // The instalment plans live inside Portfolio, not in the menu.
    expect(extraTabsFor('investor').map((t) => t.id)).not.toContain('installments')
  })

  it('reports the press of the collapse control and names its state', async () => {
    const w = await mountAt('/investor/dashboard')
    const button = w.get('.ds-nav__foot button.ds-nav__collapse')
    expect(button.attributes('aria-expanded')).toBe('true')
    expect(button.findAll('svg')).toHaveLength(2)
    await button.trigger('click')
    expect(w.emitted('toggle')).toHaveLength(1)
    await w.setProps({ collapsed: true })
    expect(w.get('.ds-nav__collapse').attributes('aria-expanded')).toBe('false')
  })

  it('has the wordmark beside the mark', async () => {
    const w = await mountAt('/investor/dashboard')
    expect(w.find('li.ds-nav__brand svg.ds-nav__wordmark').exists()).toBe(true)
  })
})
