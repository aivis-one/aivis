// =============================================================================
// PurchaseBlock -- the buying path's step 1 (K55 under a project's cover)
// =============================================================================
//
// SANKORD sells four portfolios (200 / 1,000 / 5,000 / 25,000 USD), each paid at
// once or on instalment. The block shows the portfolio switch with the bonus in the
// label, the payment switch, the parts and the quiet lines, then "Buy" -- or the
// refusal as a warning Alert with its Button. Who may buy: a visitor (sent to
// register), an investor and an agent; the block is not drawn for anyone else.
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'

const state = vi.hoisted(() => ({
  authed: false,
  role: null as string | null,
  kyc: 'approved' as string | null,
  balance: 10_000_000,
  previews: false,
}))
const push = vi.hoisted(() => vi.fn(async () => undefined))
const requireAuth = vi.hoisted(() => vi.fn(() => false))

vi.mock('vue-router', () => ({ useRouter: () => ({ push }), useRoute: () => ({}) }))
vi.mock('@/composables/safeNavigate', () => ({ safeNavigate: (p: unknown) => p }))
vi.mock('@/composables/useAuthWall', () => ({ useAuthWall: () => ({ requireAuth }) }))
vi.mock('@/composables/useReloadOnLocale', () => ({ useReloadOnLocale: () => undefined }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    get isAuthenticated() {
      return state.authed
    },
    get role() {
      return state.role
    },
    get kycStatus() {
      return state.kyc
    },
  }),
}))
vi.mock('@/stores/dashboard', () => ({
  useDashboardStore: () => ({
    get activeBalance() {
      return { confirmed: state.balance }
    },
    refresh: async () => undefined,
  }),
}))

// A portfolio: lots of 25 parts at 10 cents, so dollars x 10 = lots.
function product(dollars: number, bonus: number, plans: number[]) {
  const first =
    bonus > 0
      ? `+${bonus}% bonus parts when paid at once. On instalment, no bonus.`
      : 'Paid at once or on instalment.'
  return {
    id: `p${dollars}`,
    company_id: 'c1',
    name: `Portfolio ${dollars} USD`,
    description: `${first}\nThe agreement text.`,
    package_size: dollars * 10,
    price_per_unit_cents: 10,
    price_per_pack_cents: dollars * 100,
    available_packages: 100,
    company_name: 'SANKORD',
    installments: plans.map((months) => {
      const each = Math.floor(dollars / months)
      const last = dollars - each * (months - 1)
      return {
        id: `p${dollars}-${months}`,
        product_id: `p${dollars}`,
        name: `${months} months`,
        created_at: '2026-01-01T00:00:00Z',
        plan_config: {
          tranches: [
            ...Array.from({ length: months - 1 }, () => ({
              amount_cents: each * 100,
              units_percent: 10,
            })),
            { amount_cents: last * 100, units_percent: 50 },
          ],
          bonus_units: 0,
          agent_bonus_units: 0,
        },
      }
    }),
  }
}

const PRODUCTS = [
  product(25000, 20, [6, 12, 24]),
  product(200, 0, [6, 12, 24]),
  product(5000, 10, [6, 12, 24]),
  product(1000, 5, [6, 12, 24]),
]

vi.mock('@/api/products', () => ({
  listProducts: async () => ({ items: PRODUCTS.map((p) => ({ id: p.id })) }),
  getProduct: async (id: string) => PRODUCTS.find((p) => p.id === id),
  getPurchasePreview: async (id: string) => {
    if (!state.previews) throw new Error('no preview')
    const p = PRODUCTS.find((x) => x.id === id)!
    const m = /^\+(\d+)%/.exec(p.description)
    const pct = m ? Number(m[1]) : 0
    return { bonus_units: Math.floor((p.package_size * pct) / 100), bonus_percent: pct }
  },
}))

import PurchaseBlock from './PurchaseBlock.vue'

async function block() {
  const w = mount(PurchaseBlock, {
    props: { companyId: 'c1', companyName: 'SANKORD', sharesPerOption: 25 },
    global: {
      plugins: [
        createI18n({ legacy: false, locale: 'en', messages: { en, ru }, missingWarn: false }),
      ],
    },
  })
  await flushPromises()
  return w
}

async function choose(w: Awaited<ReturnType<typeof block>>, name: string, index: number) {
  await w.findAll(`input[name="${name}"]`)[index].setValue(true)
  await flushPromises()
}

beforeEach(() => {
  push.mockClear()
  requireAuth.mockClear()
  state.authed = false
  state.role = null
  state.kyc = 'approved'
  state.balance = 10_000_000
  state.previews = false
})

describe('PurchaseBlock for a visitor', () => {
  it('lists the portfolios cheapest first with the bonus in the label', async () => {
    const w = await block()
    const labels = w
      .findAll('fieldset.ds-segmented')[0]
      .findAll('label')
      .map((l) => l.text())
    expect(labels).toEqual(['$200', '$1,000 · +5%', '$5,000 · +10%', '$25,000 · +20%'])
  })

  it('opens on the cheapest portfolio, paid at once, with no bonus', async () => {
    const w = await block()
    expect(w.find('.ds-purchase__title').text()).toBe('Portfolio 200 USD')
    expect(w.find('.ds-purchase__parts').text()).toBe('50,000 parts')
    expect(w.find('.ds-badge').exists()).toBe(false)
  })

  it('shows the parts, the bonus parts and the price of a part for 1,000 USD', async () => {
    const w = await block()
    await choose(w, 'buy-portfolio', 1)
    expect(w.find('.ds-purchase__title').text()).toBe('Portfolio 1000 USD')
    expect(w.find('.ds-purchase__parts').text()).toContain('250,000 parts')
    expect(w.find('.ds-purchase__bonus').text()).toBe('+ 12,500 bonus')
    expect(w.find('.ds-badge--success').text()).toBe('+5% bonus')
    expect(w.find('.ds-note').text()).toBe('$0.004 per part · paid at once $1,000.00')
  })

  it('offers the payment switch of the chosen portfolio and shows the instalment without a bonus', async () => {
    const w = await block()
    await choose(w, 'buy-portfolio', 1)
    const pay = w
      .findAll('fieldset.ds-segmented')[1]
      .findAll('label')
      .map((l) => l.text())
    expect(pay).toEqual(['At once', '6 months', '12 months', '24 months'])
    await choose(w, 'buy-payment', 1)
    expect(w.find('.ds-badge').exists()).toBe(false)
    expect(w.find('.ds-purchase__bonus').exists()).toBe(false)
    const notes = w.findAll('.ds-note').map((n) => n.text())
    expect(notes).toContain('5 × $166 and the last $170 · no bonus')
    expect(notes).toContain('Each month 10% of the parts, with the last payment 50%')
  })

  it('sends a visitor to register when he presses Buy', async () => {
    const w = await block()
    await w.find('button.ds-button--primary').trigger('click')
    expect(requireAuth).toHaveBeenCalledWith('purchase')
    expect(push).not.toHaveBeenCalled()
  })
})

describe('PurchaseBlock for a signed-in buyer', () => {
  beforeEach(() => {
    state.authed = true
    state.role = 'investor'
  })

  it('reads the bonus from the server preview when there is one', async () => {
    state.previews = true
    const w = await block()
    const labels = w
      .findAll('fieldset.ds-segmented')[0]
      .findAll('label')
      .map((l) => l.text())
    expect(labels[1]).toBe('$1,000 · +5%')
  })

  it('refuses with the identity check first, as a warning Alert with its Button', async () => {
    state.kyc = 'not_started'
    const w = await block()
    const alert = w.find('.ds-alert--warning')
    expect(alert.find('.ds-alert__title').text()).toBe('Identity verification first')
    expect(w.find('button.ds-button--primary').text()).toBe('Verify your identity')
    await w.find('button.ds-button--primary').trigger('click')
    expect(push).toHaveBeenCalledWith('/verification')
  })

  it('names what is missing when the balance does not cover the portfolio', async () => {
    state.balance = 5_000
    const w = await block()
    await flushPromises()
    const alert = w.find('.ds-alert--warning')
    expect(alert.find('.ds-alert__title').text()).toBe('Short of $150.00')
    expect(alert.find('.ds-alert__text').text()).toBe(
      'Your balance is $50.00; the portfolio costs $200.00.',
    )
    expect(w.find('button.ds-button--primary').text()).toBe('Top up the balance')
  })

  it('compares the first payment with the balance on an instalment', async () => {
    state.balance = 5_000
    const w = await block()
    await choose(w, 'buy-portfolio', 1)
    await choose(w, 'buy-payment', 1)
    const alert = w.find('.ds-alert--warning')
    expect(alert.find('.ds-alert__text').text()).toBe(
      'Your balance is $50.00; the first payment is $166.00.',
    )
  })

  it('leads Buy to the confirmation: a payment at once, then an instalment', async () => {
    const w = await block()
    await choose(w, 'buy-portfolio', 1)
    await w.find('button.ds-button--primary').trigger('click')
    expect(push).toHaveBeenLastCalledWith({ name: 'investor-purchase', params: { id: 'p1000' } })
    await choose(w, 'buy-payment', 2)
    await w.find('button.ds-button--primary').trigger('click')
    expect(push).toHaveBeenLastCalledWith({
      name: 'investor-installment',
      params: { id: 'p1000' },
      query: { plan: 'p1000-12' },
    })
  })

  it('uses the agent routes for an agent, who buys by the same path', async () => {
    state.role = 'agent'
    const w = await block()
    await w.find('button.ds-button--primary').trigger('click')
    expect(push).toHaveBeenLastCalledWith({ name: 'agent-purchase', params: { id: 'p200' } })
  })
})

describe('PurchaseBlock for the others', () => {
  it('is not drawn for a staff account', async () => {
    state.authed = true
    state.role = 'staff'
    const w = await block()
    expect(w.find('.ds-card').exists()).toBe(false)
  })
})
