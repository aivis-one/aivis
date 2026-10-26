// =============================================================================
// Finance > Invoices -- WHAT THE ADMINISTRATOR SEES AND SENDS
// =============================================================================
//
// One mount with the API mocked, asserting through the rendered text
// (translation keys: the test catalogue is empty on purpose, see test-setup.ts).
// Axes: the list EMPTY, FULL and FAILED; an invoice credited and not credited;
// a confirmation sent, refused (409) and failed.
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/api/admin', () => ({
  fetchCryptoInvoices: vi.fn(),
  confirmCryptoInvoice: vi.fn(),
  fetchUsers: vi.fn(async () => ({ items: [], total: 0, page: 1, per_page: 8 })),
}))

import * as admin from '@/api/admin'
import { ApiResponseError } from '@/api/client'
import StaffCryptoInvoicesView from './StaffCryptoInvoicesView.vue'

const fetchCryptoInvoices = vi.mocked(admin.fetchCryptoInvoices)
const confirmCryptoInvoice = vi.mocked(admin.confirmCryptoInvoice)

function invoice(id: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    user_id: `user-${id}-aaaa-bbbb`,
    user_email: 'ada@example.com',
    user_name: 'Ada Lovelace',
    network: 'USDT-TRC20',
    amount_cents: 12_500,
    status: 'expired',
    created_at: '2026-10-20T10:00:00Z',
    expires_at: '2026-10-20T11:00:00Z',
    credited: false,
    credited_by: null,
    payment_id: null,
    ...extra,
  }
}

function listIs(items: unknown[]) {
  fetchCryptoInvoices.mockResolvedValue({
    items,
    total: items.length,
    page: 1,
    per_page: 20,
  } as never)
}

function modalButton(label: string): HTMLButtonElement {
  return Array.from(document.body.querySelectorAll('.ds-dialog__panel button')).find((b) =>
    (b.textContent ?? '').includes(label),
  ) as HTMLButtonElement
}

beforeEach(() => {
  setActivePinia(createPinia())
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('the list', () => {
  it('offers the hand confirmation on an uncredited invoice only, and names who credited the others', async () => {
    listIs([
      invoice('i1'),
      invoice('i2', { credited: true, credited_by: 'service' }),
      invoice('i3', { credited: true, credited_by: 'manual' }),
    ])
    const wrapper = mount(StaffCryptoInvoicesView)
    await flushPromises()
    const rows = wrapper.findAll('.inv-list .inv-item')
    expect(rows).toHaveLength(3)
    expect(rows[0]!.find('.inv-item__confirm').exists()).toBe(true)
    expect(rows[1]!.find('.inv-item__confirm').exists()).toBe(false)
    expect(rows[1]!.text()).toContain('staff.invoices.creditedService')
    expect(rows[2]!.find('.inv-item__confirm').exists()).toBe(false)
    expect(rows[2]!.text()).toContain('staff.invoices.creditedManual')
    expect(rows[0]!.text()).toContain('Ada Lovelace')
    expect(rows[0]!.text()).toContain('$125.00')
    wrapper.unmount()
  })

  it('says there are no invoices when the answer is empty', async () => {
    listIs([])
    const wrapper = mount(StaffCryptoInvoicesView)
    await flushPromises()
    expect(wrapper.text()).toContain('staff.invoices.empty')
    wrapper.unmount()
  })

  it('shows a failed read as a failure, not as an empty list', async () => {
    fetchCryptoInvoices.mockRejectedValue(new Error('500'))
    const wrapper = mount(StaffCryptoInvoicesView)
    await flushPromises()
    expect(wrapper.text()).toContain('common.error')
    expect(wrapper.text()).not.toContain('staff.invoices.empty')
    wrapper.unmount()
  })

  it('reads the list again for the chosen person and status', async () => {
    listIs([])
    const wrapper = mount(StaffCryptoInvoicesView)
    await flushPromises()
    wrapper.findComponent({ name: 'UserPicker' }).vm.$emit('update:modelValue', 'u1')
    await flushPromises()
    expect(fetchCryptoInvoices).toHaveBeenLastCalledWith(
      expect.objectContaining({ user_id: 'u1', page: 1 }),
    )
    await wrapper.findAll('.ds-chip')[2]!.trigger('click')
    await flushPromises()
    expect(fetchCryptoInvoices).toHaveBeenLastCalledWith(
      expect.objectContaining({ user_id: 'u1', status: 'awaiting_confirmations' }),
    )
    wrapper.unmount()
  })
})

describe('the confirmation', () => {
  it('shows the client and the amount, waits for a reason, sends it and reads the list again', async () => {
    listIs([invoice('i1')])
    confirmCryptoInvoice.mockResolvedValue({} as never)
    const wrapper = mount(StaffCryptoInvoicesView, { attachTo: document.body })
    await flushPromises()
    await wrapper.find('.inv-item__confirm').trigger('click')
    await flushPromises()

    const panel = document.body.querySelector('.ds-dialog__panel')!
    expect(panel.textContent).toContain('Ada Lovelace')
    expect(panel.textContent).toContain('$125.00')
    // No reason, no confirmation.
    expect(modalButton('common.confirm').disabled).toBe(true)

    const input = panel.querySelector('input') as HTMLInputElement
    input.value = 'paid by bank transfer'
    input.dispatchEvent(new Event('input'))
    await flushPromises()
    expect(modalButton('common.confirm').disabled).toBe(false)

    const before = fetchCryptoInvoices.mock.calls.length
    modalButton('common.confirm').click()
    await flushPromises()
    expect(confirmCryptoInvoice).toHaveBeenCalledWith('i1', { reason: 'paid by bank transfer' })
    expect(fetchCryptoInvoices.mock.calls.length).toBeGreaterThan(before)
    wrapper.unmount()
  })

  it('reads the list again when the server says the invoice is already credited (409)', async () => {
    listIs([invoice('i1')])
    confirmCryptoInvoice.mockRejectedValue(new ApiResponseError(409, 'already credited'))
    const wrapper = mount(StaffCryptoInvoicesView, { attachTo: document.body })
    await flushPromises()
    await wrapper.find('.inv-item__confirm').trigger('click')
    await flushPromises()
    const input = document.body.querySelector('.ds-dialog__panel input') as HTMLInputElement
    input.value = 'second try'
    input.dispatchEvent(new Event('input'))
    await flushPromises()
    const before = fetchCryptoInvoices.mock.calls.length
    modalButton('common.confirm').click()
    await flushPromises()
    expect(fetchCryptoInvoices.mock.calls.length).toBeGreaterThan(before)
    wrapper.unmount()
  })
})
