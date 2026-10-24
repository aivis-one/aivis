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

async function mountHeader(spec: ScreenHeaderSpec) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  })
  await router.push('/investor/portfolio')
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

  it('is a button calling the handler a getter returns', async () => {
    const close = vi.fn()
    const { header, owner } = await mountHeader({ title: 'Thread', back: () => close })
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
