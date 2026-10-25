// =============================================================================
// TransactionDetailSheet -- a purchase entry in parts and the price of a part
// =============================================================================
//
// A purchase entry carries the lots and the lot's price; the sheet shows the parts
// (lots x the project's parts per lot) and the price of a part, three decimals, with
// the total in the header. Until the project's parts per lot is known the two lines
// are left out, never shown in lots.
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'

const getTransaction = vi.fn()
const getCompany = vi.fn()
vi.mock('@/api/transactions', () => ({ getTransaction: (id: string) => getTransaction(id) }))
vi.mock('@/api/companies', () => ({ getCompany: (id: string) => getCompany(id) }))

import TransactionDetailSheet from './TransactionDetailSheet.vue'
import { resetSharesPerOptionCache } from '@/composables/useSharesPerOption'

const purchase = {
  id: 't1',
  user_id: 'u1',
  type: 'purchase:completed',
  amount_cents: -40,
  currency: 'USD',
  created_at: '2026-10-23T10:00:00Z',
  details: { company_id: 'c1', units: 4, price_per_unit_cents: 10, legal_basis: 'sale' },
}

async function sheet(locale: 'en' | 'ru') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  })
  await router.push('/investor/transactions')
  await router.isReady()
  const w = mount(TransactionDetailSheet, {
    props: { open: true, transactionId: 't1' },
    global: {
      plugins: [
        router,
        createI18n({ legacy: false, locale, messages: { en, ru }, missingWarn: false }),
      ],
      stubs: { CBottomSheet: { template: '<div><slot /></div>' } },
    },
  })
  await flushPromises()
  return w
}

const rows = (w: Awaited<ReturnType<typeof sheet>>) =>
  w.findAll('.ds-kv__row').map((r) => r.text().replace(/\s+/g, ' '))

beforeEach(() => {
  getTransaction.mockReset()
  getCompany.mockReset()
  resetSharesPerOptionCache()
  getTransaction.mockResolvedValue(purchase)
})

describe('TransactionDetailSheet', () => {
  it('shows the parts and the price of a part, not the lots', async () => {
    getCompany.mockResolvedValue({ shares_per_option: 25 })
    const w = await sheet('en')
    expect(rows(w)).toContain('Parts100')
    expect(rows(w)).toContain('Price of a part$0.004')
    expect(w.text()).toContain('$0.40')
    expect(rows(w)).not.toContain('Parts4')
  })

  it('leaves the two lines out while the parts per lot is unknown', async () => {
    getCompany.mockRejectedValue(new Error('404'))
    const w = await sheet('en')
    expect(rows(w).some((r) => r.startsWith('Parts'))).toBe(false)
    expect(rows(w).some((r) => r.startsWith('Price of a part'))).toBe(false)
    expect(rows(w).some((r) => r.startsWith('Legal Basis'))).toBe(true)
  })

  it('labels them in Russian', async () => {
    getCompany.mockResolvedValue({ shares_per_option: 25 })
    const w = await sheet('ru')
    expect(rows(w).some((r) => r.startsWith('Части100'))).toBe(true)
    expect(rows(w).some((r) => r.startsWith('Цена части'))).toBe(true)
  })
})
