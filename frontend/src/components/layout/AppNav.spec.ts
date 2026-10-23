// The frame's one menu: links, the current mark by path prefix, the mark of AIVIS.

import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppNav from './AppNav.vue'
import { INVESTOR_TABS } from '@/router/tabs'

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(AppNav, {
    props: { items: INVESTOR_TABS },
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
})
