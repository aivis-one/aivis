// The frame's header: the back control is a link for a route, one step back for
// `true`, and a button calling the screen's own handler for a function.

import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createI18n } from 'vue-i18n'
import AppHeader from './AppHeader.vue'
import { useScreenHeader } from './screenHeader'
import type { ScreenHeaderSpec } from './screenHeader'
import type { Shell } from '@/router/helpers'

async function mountHeader(
  spec: ScreenHeaderSpec,
  at = '/investor/portfolio',
  shell?: Shell,
  name?: string,
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/:pathMatch(.*)*', component: { template: '<div />' }, meta: { shell }, name },
    ],
  })
  await router.push(at)
  await router.isReady()
  const i18n = createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: { common: { back: 'Back' }, app: { name: 'AIVIS' } } },
  })
  const screen = defineComponent({
    setup() {
      useScreenHeader(spec)
      return () => h('div')
    },
  })
  const header = mount(AppHeader, { global: { plugins: [router, createPinia(), i18n] } })
  const owner = mount(screen)
  await flushPromises()
  return { header, owner }
}

describe('AppHeader back control', () => {
  it('is a link for a route', async () => {
    const { header, owner } = await mountHeader({ title: 'Thread', back: '/investor/news' })
    const back = header.find('.ds-header__lead a.ds-button')
    expect(back.exists()).toBe(true)
    expect(back.attributes('href')).toBe('/investor/news')
    owner.unmount()
  })

  it('is a button calling the handler of { handler }', async () => {
    const close = vi.fn()
    const { header, owner } = await mountHeader({
      title: 'Thread',
      back: () => ({ handler: close }),
    })
    const back = header.find('.ds-header__lead button.ds-button')
    expect(back.exists()).toBe(true)
    expect(header.find('.ds-header__lead a.ds-button').exists()).toBe(false)
    await back.trigger('click')
    expect(close).toHaveBeenCalledTimes(1)
    owner.unmount()
  })

  it('draws no back control while the getter returns nothing', async () => {
    const { header, owner } = await mountHeader({ title: 'List', back: () => undefined })
    expect(header.find('.ds-header__lead .ds-button').exists()).toBe(false)
    owner.unmount()
  })
})

describe('AppHeader default way back', () => {
  it('gives a buyer screen with no back of its own one step back', async () => {
    const { header, owner } = await mountHeader(
      { title: 'Balance' },
      '/investor/balance',
      'investor',
    )
    const back = header.find('.ds-header__lead button.ds-button')
    expect(back.exists()).toBe(true)
    owner.unmount()
  })

  it('goes to the dashboard when there was no page before', async () => {
    const { header, owner } = await mountHeader(
      { title: 'Balance' },
      '/investor/balance',
      'investor',
    )
    const router = header.vm.$router
    await header.find('.ds-header__lead button.ds-button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/investor/dashboard')
    owner.unmount()
  })

  it('gives the dashboard itself no back control', async () => {
    const { header, owner } = await mountHeader(
      { title: 'Dashboard' },
      '/investor/dashboard',
      'investor',
      'investor-dashboard',
    )
    expect(header.find('.ds-header__lead .ds-button').exists()).toBe(false)
    owner.unmount()
  })

  it('leaves a screen outside the cabinets to its own choice', async () => {
    const { header, owner } = await mountHeader({ title: 'Storefront' }, '/public/companies')
    expect(header.find('.ds-header__lead button.ds-button').exists()).toBe(false)
    owner.unmount()
  })
})
