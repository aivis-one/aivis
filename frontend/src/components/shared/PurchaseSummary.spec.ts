// =============================================================================
// PurchaseSummary -- the Purchase block's lines (K55)
// =============================================================================
//
// A 1,000 USD portfolio of SANKORD: 10,000 lots of 25 parts at 10 cents. Paid at
// once it shows the parts, the bonus in the success colour with its sign in the
// text, the price of a part and the total; on an instalment it shows the money of
// the instalment, "no bonus" and the parts by month, and no bonus anywhere else.
// =============================================================================

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'
import { parsePlanConfig } from '@/utils/installmentPlans'
import PurchaseSummary from './PurchaseSummary.vue'

function i18n(locale: 'en' | 'ru') {
  return createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false })
}

const SIX_MONTHS = parsePlanConfig({
  tranches: [
    ...Array.from({ length: 5 }, () => ({ amount_cents: 16_600, units_percent: 10 })),
    { amount_cents: 17_000, units_percent: 50 },
  ],
})!

const BASE = {
  title: 'SANKORD · Portfolio 1,000 USD',
  lots: 10_000,
  lotPriceCents: 10,
  sharesPerOption: 25,
  totalCents: 100_000,
}

function mountSummary(props: Record<string, unknown>, locale: 'en' | 'ru' = 'en') {
  return mount(PurchaseSummary, {
    props: { ...BASE, ...props } as never,
    global: { plugins: [i18n(locale)] },
  })
}

describe('PurchaseSummary, paid at once', () => {
  const w = mountSummary({ bonusPercent: 5, bonusLots: 500, plan: null })

  it('shows the parts, never the lots', () => {
    expect(w.find('.ds-purchase__parts').text()).toContain('250,000 parts')
    expect(w.text()).not.toContain('10,000')
  })

  it('shows the bonus parts with the sign in the text, in the success class', () => {
    const bonus = w.find('.ds-purchase__bonus')
    expect(bonus.text()).toBe('+ 12,500 bonus')
  })

  it('shows the bonus badge as a success badge', () => {
    const badge = w.find('.ds-purchase__head .ds-badge')
    expect(badge.classes()).toContain('ds-badge--success')
    expect(badge.text()).toBe('+5% bonus')
  })

  it('shows the price of a part and the total in dollars and cents', () => {
    expect(w.find('.ds-note').text()).toBe('$0.004 per part · paid at once $1,000.00')
  })
})

describe('PurchaseSummary, a portfolio without a bonus', () => {
  it('says so in words and draws no badge', () => {
    const w = mountSummary({ bonusPercent: 0, bonusLots: 0, plan: null })
    expect(w.find('.ds-badge').exists()).toBe(false)
    expect(w.find('.ds-purchase__bonus').exists()).toBe(false)
    expect(w.find('.ds-note').text()).toContain('no bonus')
  })
})

describe('PurchaseSummary, on instalment', () => {
  const w = mountSummary({
    bonusPercent: 5,
    bonusLots: 500,
    plan: SIX_MONTHS,
    planName: '6 months',
  })

  it('shows no bonus, whatever the portfolio has for a payment at once', () => {
    expect(w.find('.ds-badge').exists()).toBe(false)
    expect(w.find('.ds-purchase__bonus').exists()).toBe(false)
    expect(w.find('.ds-purchase__parts').text()).toBe('250,000 parts over 6 months')
  })

  it('shows the money of the instalment marked "no bonus"', () => {
    const notes = w.findAll('.ds-note').map((n) => n.text())
    expect(notes).toContain('5 × $166 and the last $170 · no bonus')
  })

  it('shows the parts by month', () => {
    const notes = w.findAll('.ds-note').map((n) => n.text())
    expect(notes).toContain('Each month 10% of the parts, with the last payment 50%')
  })
})

describe('PurchaseSummary, in Russian', () => {
  it('says parts and the part price in Russian', () => {
    const w = mountSummary({ bonusPercent: 5, bonusLots: 500, plan: null }, 'ru')
    expect(w.find('.ds-purchase__parts').text()).toContain('частей')
    expect(w.find('.ds-note').text()).toContain('0,004')
    expect(w.find('.ds-purchase__bonus').text()).toContain('бонусных')
  })
})
