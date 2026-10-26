// =============================================================================
// InvestorDepositView -- THE TRIPLE CLICK ON THE NETWORK WARNING
// =============================================================================
//
// A person who paid another way triple-clicks the orange network warning, and
// the screen asks the server to pass the invoice to an administrator. One or
// two clicks must do nothing, three clicks spread wider than the window must do
// nothing. The sent line shows ONLY after the server took the request; a
// failed request shows its own line and never the sent one; a reload of an
// invoice the server says was asked for shows the waiting line; an invoice
// credited by hand shows the confirmed state.
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
  requestManualConfirmation: vi.fn(),
  submitInvoiceTxid: vi.fn(),
}))
vi.mock('@/api/payments', () => api)

import { ApiNetworkError, ApiResponseError } from '@/api/client'
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
  manual_requested_at: null,
  manually_credited: false,
}

const LINE = 'inv.deposit.manualRequested'
const FAILED = 'inv.deposit.manualFailed'

async function mountWith(invoice: Record<string, unknown>): Promise<VueWrapper> {
  api.getCurrentInvoice.mockImplementation(async (network: string) =>
    network === 'USDT-TRC20' ? invoice : null,
  )
  const w = mount(InvestorDepositView)
  await flushPromises()
  return w
}

const mountOpen = (): Promise<VueWrapper> => mountWith(OPEN)

async function clickWarning(w: VueWrapper, times: number, gapMs: number): Promise<void> {
  const warning = w.find('.dv-warning')
  for (let i = 0; i < times; i++) {
    if (i > 0) vi.advanceTimersByTime(gapMs)
    await warning.trigger('click')
  }
  await flushPromises()
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
    expect(api.requestManualConfirmation).not.toHaveBeenCalled()
  })

  it('does nothing on two clicks', async () => {
    const w = await mountOpen()
    await clickWarning(w, 2, 100)
    expect(w.text()).not.toContain(LINE)
    expect(api.requestManualConfirmation).not.toHaveBeenCalled()
  })

  it('does nothing on three clicks spread wider than the window', async () => {
    const w = await mountOpen()
    await clickWarning(w, 3, 500)
    expect(w.text()).not.toContain(LINE)
    expect(api.requestManualConfirmation).not.toHaveBeenCalled()
  })

  it('sends the request on three quick clicks and shows the line only once it succeeded', async () => {
    let resolve: (value: unknown) => void = () => {}
    api.requestManualConfirmation.mockImplementation(
      () => new Promise((r) => (resolve = r)),
    )
    const w = await mountOpen()
    await clickWarning(w, 3, 100)
    expect(api.requestManualConfirmation).toHaveBeenCalledTimes(1)
    expect(api.requestManualConfirmation).toHaveBeenCalledWith('inv-1')
    // Not yet answered: no line.
    expect(w.text()).not.toContain(LINE)

    resolve({ invoice_id: 'inv-1', requested_at: '2026-10-26T10:00:00Z', already_requested: false })
    await flushPromises()
    const line = w.findAll('[role="status"]').filter((n) => n.text() === LINE)
    expect(line).toHaveLength(1)
    expect(w.text()).not.toContain(FAILED)
  })

  it.each([
    ['the network', new ApiNetworkError('offline')],
    ['a server error', new ApiResponseError(500, 'boom')],
  ])('shows the failure line, never the sent line, when %s fails', async (_name, error) => {
    api.requestManualConfirmation.mockRejectedValue(error)
    const w = await mountOpen()
    await clickWarning(w, 3, 100)
    expect(w.text()).not.toContain(LINE)
    const alert = w.findAll('[role="alert"]').filter((n) => n.text() === FAILED)
    expect(alert).toHaveLength(1)
  })

  it('may be asked again after a failure', async () => {
    api.requestManualConfirmation.mockRejectedValueOnce(new ApiResponseError(503, 'down'))
    api.requestManualConfirmation.mockResolvedValueOnce({
      invoice_id: 'inv-1',
      requested_at: '2026-10-26T10:00:00Z',
      already_requested: false,
    })
    const w = await mountOpen()
    await clickWarning(w, 3, 100)
    expect(w.text()).toContain(FAILED)
    vi.advanceTimersByTime(1000)
    await clickWarning(w, 3, 100)
    expect(w.text()).toContain(LINE)
    expect(w.text()).not.toContain(FAILED)
  })

  it('shows the waiting line on a reload of an invoice already asked for, and sends nothing', async () => {
    const w = await mountWith({ ...OPEN, manual_requested_at: '2026-10-26T09:00:00Z' })
    expect(w.text()).toContain(LINE)
    await clickWarning(w, 3, 100)
    expect(api.requestManualConfirmation).not.toHaveBeenCalled()
  })

  it('shows the confirmed state for an invoice an administrator credited, and no waiting line', async () => {
    const w = await mountWith({
      ...OPEN,
      manual_requested_at: '2026-10-26T09:00:00Z',
      manually_credited: true,
    })
    expect(w.text()).not.toContain(LINE)
    expect(w.text()).toContain('inv.deposit.status.confirmed')
    expect(w.find('.ds-alert--success').exists()).toBe(true)
    await clickWarning(w, 3, 100)
    expect(api.requestManualConfirmation).not.toHaveBeenCalled()
  })

  it('re-reads the invoice when the server says it is already credited (409)', async () => {
    api.requestManualConfirmation.mockRejectedValue(new ApiResponseError(409, 'credited'))
    api.getInvoice.mockResolvedValue({ ...OPEN, manually_credited: true })
    const w = await mountOpen()
    await clickWarning(w, 3, 100)
    expect(api.getInvoice).toHaveBeenCalledWith('inv-1')
    expect(w.text()).not.toContain(LINE)
    expect(w.text()).not.toContain(FAILED)
    expect(w.text()).toContain('inv.deposit.status.confirmed')
  })
})

describe('InvestorDepositView, the words of the lines', () => {
  it('carries the agreed words in Russian and English', () => {
    expect(ru.inv.deposit.manualRequested).toBe(
      'Заявка отправлена администратору. Он проверит платёж и подтвердит пополнение.',
    )
    expect(en.inv.deposit.manualRequested).toBe(
      'Your request has been sent to the administrator. They will check the payment and confirm the top-up.',
    )
    expect(ru.inv.deposit.manualFailed).toBe('Не удалось отправить заявку. Попробуйте ещё раз.')
    expect(en.inv.deposit.manualFailed).toBe('The request could not be sent. Please try again.')
  })
})
