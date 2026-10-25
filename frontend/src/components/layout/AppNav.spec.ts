// The frame's one menu: links, the current mark by path prefix, the mark of AIVIS.

import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppNav from './AppNav.vue'
import { extraTabsFor, INVESTOR_TABS } from '@/router/tabs'
import { useAuthStore } from '@/stores/auth'

async function mountAt(path: string, extra = false) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(AppNav, {
    props: { items: INVESTOR_TABS, extra: extra ? extraTabsFor('investor') : [] },
    global: { plugins: [router, createPinia(), createI18n({ legacy: false, locale: 'en', messages: { en } })] },
  })
  await flushPromises()
  return w
}

describe('AppNav', () => {
  it('is one nav landmark holding a link for each item, with the mark of AIVIS ahead of them', async () => {
    const w = await mountAt('/investor/dashboard')
    expect(w.findAll('nav.ds-nav')).toHaveLength(1)
    expect(w.findAll('a.ds-navitem')).toHaveLength(INVESTOR_TABS.length)
    expect(w.find('li.ds-nav__brand div.ds-nav__logo img.ds-nav__mark').exists()).toBe(true)
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

  it('shows the mark as a static image, not a link', async () => {
    const w = await mountAt('/investor/dashboard')
    expect(w.find('li.ds-nav__brand a').exists()).toBe(false)
    expect(w.get('li.ds-nav__brand .ds-nav__logo').attributes('role')).toBe('img')
    expect(w.get('li.ds-nav__brand .ds-nav__logo').attributes('aria-label')).toBe('AIVIS')
  })

  it('reports the press of the collapse control and names its state', async () => {
    const w = await mountAt('/investor/dashboard')
    const button = w.get('.ds-nav__foot button.ds-nav__collapse')
    expect(button.attributes('aria-expanded')).toBe('true')
    await button.trigger('click')
    expect(w.emitted('toggle')).toHaveLength(1)
    await w.setProps({ collapsed: true })
    expect(w.get('.ds-nav__collapse').attributes('aria-expanded')).toBe('false')
  })

  it('draws the collapse control with the panel icons and the word Collapse, then Expand', async () => {
    const w = await mountAt('/investor/dashboard')
    const button = w.get('.ds-nav__collapse')
    const uses = button.findAll('svg use').map((u) => u.attributes('href'))
    expect(uses).toEqual(['#i-panel-left-close', '#i-panel-left-open'])
    expect(button.get('.ds-navitem__label').text()).toBe('Collapse')
    await w.setProps({ collapsed: true })
    expect(w.get('.ds-nav__collapse .ds-navitem__label').text()).toBe('Expand')
  })

  it('ends the foot with the Log out item, which signs the person out', async () => {
    const w = await mountAt('/investor/dashboard')
    const items = w.findAll('.ds-nav__foot > button')
    expect(items.map((i) => i.classes())).toEqual([
      expect.arrayContaining(['ds-nav__collapse']),
      expect.arrayContaining(['ds-nav__logout']),
    ])
    const logout = items[1]!
    expect(logout.get('.ds-navitem__label').text()).toBe('Log out')
    expect(logout.get('svg use').attributes('href')).toBe('#i-log-out')
    const store = useAuthStore()
    const spy = vi.spyOn(store, 'logout').mockResolvedValue(undefined)
    await logout.trigger('click')
    await flushPromises()
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('has the wordmark beside the mark', async () => {
    const w = await mountAt('/investor/dashboard')
    expect(w.find('li.ds-nav__brand svg.ds-nav__wordmark').exists()).toBe(true)
  })
})

describe('the phone bar marks the current section', () => {
  const css = readFileSync('src/styles/ds/components.css', 'utf8')

  it('with the tinted tab of the rails and no dot', () => {
    expect(css).toMatch(
      /\.ds-navitem\[aria-current="page"\] \{ color: var\(--primary\); background: var\(--primary-subtle\); \}/,
    )
    // The only mark drawn before the current item is the rails' bar, never a dot of the accent colour.
    const marks = css.match(/\.ds-navitem\[aria-current="page"\]::before \{[^}]*\}/g) ?? []
    expect(marks.join(' ')).not.toMatch(/--accent/)
  })

  it('has the foot words in Russian too', () => {
    const nav = (ru as { common: { nav: Record<string, string> } }).common.nav
    expect(nav.collapse).toBe('Свернуть')
    expect(nav.expand).toBe('Развернуть')
    expect(nav.logout).toBe('Выйти')
  })
})
