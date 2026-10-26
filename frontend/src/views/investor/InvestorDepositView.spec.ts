// =============================================================================
// InvestorDepositView -- THE TRIPLE CLICK ON THE NETWORK WARNING
// =============================================================================
//
// A person who paid another way triple-clicks the orange network warning, and
// the hash card's status line says the request went to an administrator. One or
// two clicks must do nothing, three clicks spread wider than the window must do
// nothing, and the screen must call no service for it.
// =============================================================================

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  useRoute: () => ({ query: {} }),
}))
vi.mock('@/composables/safeNavigate', () => ({ safeNavigate: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ kycStatus: 'not_started' }) }))
vi.mock('@/components/layout/screenHeader', () => ({ useScreenHeader: vi.fn() }))
vi.mock('qrcode', () => ({ default: { toString: vi.fn(async () => '<svg></svg>') } }))

const api = vi.hoisted(() => ({
  createInvoice: vi.fn(),
  getCurrentInvoice: vi.fn(),
  getInvoice: vi.fn(),
  submitInvoiceTxid: vi.fn(),
}))
vi.mock('@/api/payments', () => api)

import en from '@/i18n/locales/en.json'
import ru from '@/i18n/locales/ru.json'
import InvestorDepositView from './InvestorDepositView.vue'

const OPEN = {
  id: 'inv-1',
  network: 'USDT-TRC20',
  address: 'TXexampleaddress',
  invoice_amount_cents: 10000,
  status: 'created',
  expires_at: null,
  attempts_remaining: 3,
}

const LINE = 'inv.deposit.manualRequested'

async function mountOpen(): Promise<VueWrapper> {
  api.getCurrentInvoice.mockImplementation(async (network: string) =>
    network === 'USDT-TRC20' ? OPEN : null,
  )
  const w = mount(InvestorDepositView)
  await flushPromises()
  return w
}

async function clickWarning(w: VueWrapper, times: number, gapMs: number): Promise<void> {
  const warning = w.find('.dv-warning')
  for (let i = 0; i < times; i++) {
    if (i > 0) vi.advanceTimersByTime(gapMs)
    await warning.trigger('click')
  }
}

describe('InvestorDepositView, the triple click on the network warning', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] })
    vi.setSystemTime(new Date('2026-10-26T10:00:00Z'))
    Object.values(api).forEach((f) => f.mockReset())
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows the warning on an open invoice', async () => {
    const w = await mountOpen()
    expect(w.find('.dv-warning').exists()).toBe(true)
    expect(w.text()).not.toContain(LINE)
  })

  it('does nothing on one click', async () => {
    const w = await mountOpen()
    await clickWarning(w, 1, 0)
    expect(w.text()).not.toContain(LINE)
  })

  it('does nothing on two clicks', async () => {
    const w = await mountOpen()
    await clickWarning(w, 2, 100)
    expect(w.text()).not.toContain(LINE)
  })

  it('does nothing on three clicks spread wider than the window', async () => {
    const w = await mountOpen()
    await clickWarning(w, 3, 500)
    expect(w.text()).not.toContain(LINE)
  })

  it('shows the line in the status line on three quick clicks, and calls no service', async () => {
    const w = await mountOpen()
    const calls = Object.values(api).map((f) => f.mock.calls.length)
    await clickWarning(w, 3, 100)
    const line = w.findAll('[role="status"]').filter((n) => n.text() === LINE)
    expect(line).toHaveLength(1)
    expect(Object.values(api).map((f) => f.mock.calls.length)).toEqual(calls)
  })
})

describe('InvestorDepositView, the words of the line', () => {
  it('carries the same words in Russian and English', () => {
    expect(ru.inv.deposit.manualRequested).toBe('Заявка отправлена на подтверждение администратору')
    expect(en.inv.deposit.manualRequested).toBe(
      'Your request has been sent to an administrator for confirmation',
    )
  })
})
