// =============================================================================
// PortfolioView -- the holdings in parts and the price of a part
// =============================================================================
//
// A position counts lots; the buyer sees parts. 4 lots of 25 parts bought for 40
// cents are 100 parts at 0.004 USD, and the hero adds the parts of every project in
// that project's own parts per lot.
// =============================================================================

import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'

const position = (over: Record<string, unknown>) => ({
  company_id: 'c1',
  company_name: 'Acme',
  logo_url: null,
  logo_dark_url: null,
  shares_per_option: 25,
  total_units: 4,
  sale_units: 4,
  gift_units: 0,
  total_paid_cents: 40,
  avg_price_cents: 10,
  current_price_cents: 10,
  current_value_cents: 40,
  purchases_count: 1,
  ...over,
})

vi.mock('@/api/portfolio', () => ({
  getMyPortfolio: async () => ({
    positions: [
      position({}),
      position({
        company_id: 'c2',
        company_name: 'Beta',
        shares_per_option: 1000,
        total_units: 2,
        sale_units: 2,
        total_paid_cents: 2000,
      }),
    ],
  }),
}))

import PortfolioView from './PortfolioView.vue'

async function portfolio(locale: 'en' | 'ru') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/investor/portfolio',
        name: 'investor-portfolio',
        component: { template: '<div />' },
      },
      {
        path: '/investor/plans',
        name: 'investor-installment-plans',
        component: { template: '<div />' },
      },
      {
        path: '/investor/portfolio/:id',
        name: 'investor-company-position',
        component: { template: '<div />' },
      },
      {
        path: '/investor/companies',
        name: 'investor-companies',
        component: { template: '<div />' },
      },
    ],
  })
  await router.push('/investor/portfolio')
  await router.isReady()
  const w = mount(PortfolioView, {
    global: {
      plugins: [
        router,
        createPinia(),
        createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false }),
      ],
      stubs: { PendingGifts: true },
    },
  })
  await flushPromises()
  return w
}

describe('PortfolioView', () => {
  it('shows each position in parts with the average price of a part', async () => {
    const w = await portfolio('en')
    const cards = w.findAll('.ds-card')
    const facts = (i: number) =>
      cards[i]?.findAll('.ds-kv__row').map((r) => r.text().replace(/\s+/g, ' ')) ?? []
    const all = cards.map((_, i) => facts(i)).flat()
    expect(all).toContain('Parts100')
    expect(all).toContain('Avg. price of a part$0.004')
    expect(all).toContain('Parts2,000')
    expect(all).toContain('Avg. price of a part$0.010')
  })

  it('adds the parts of every project in its own parts per lot', async () => {
    const w = await portfolio('en')
    // 4 x 25 + 2 x 1000
    expect(w.text()).toContain('2,100')
  })

  it('says parts in Russian too', async () => {
    const w = await portfolio('ru')
    expect(w.text()).toContain('Части')
    expect(w.text()).not.toContain('Юниты')
  })
})
