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

const routeQuery = vi.hoisted(() => ({ value: {} as Record<string, string> }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: routeQuery.value }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/api/admin', () => ({
  fetchCryptoInvoices: vi.fn(),
  confirmCryptoInvoice: vi.fn(),
  addCryptoInvoiceNote: vi.fn(),
  fetchUsers: vi.fn(async () => ({ items: [], total: 0, page: 1, per_page: 8 })),
}))

import * as admin from '@/api/admin'
import { ApiResponseError } from '@/api/client'
import StaffCryptoInvoicesView from './StaffCryptoInvoicesView.vue'

const fetchCryptoInvoices = vi.mocked(admin.fetchCryptoInvoices)
const confirmCryptoInvoice = vi.mocked(admin.confirmCryptoInvoice)
const addCryptoInvoiceNote = vi.mocked(admin.addCryptoInvoiceNote)

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
    manual_requested_at: null,
    manual_request_open: false,
    confirm_reason: null,
    notes: [],
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
  routeQuery.value = {}
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

describe("the client's request, the basis and the notes", () => {
  it('marks an invoice with an open request and shows the basis of a hand confirmation', async () => {
    listIs([
      invoice('i1', { manual_requested_at: '2026-10-25T09:00:00Z', manual_request_open: true }),
      invoice('i2', {
        credited: true,
        credited_by: 'manual',
        manual_requested_at: '2026-10-25T09:00:00Z',
        confirm_reason: 'paid by bank transfer',
      }),
      invoice('i3'),
    ])
    const wrapper = mount(StaffCryptoInvoicesView)
    await flushPromises()
    const rows = wrapper.findAll('.inv-list .inv-item')
    expect(rows[0]!.find('.inv-item__requested').exists()).toBe(true)
    expect(rows[0]!.text()).toContain('staff.invoices.manualRequested')
    expect(rows[0]!.text()).toContain('staff.invoices.requestedAt')
    expect(rows[1]!.find('.inv-item__requested').exists()).toBe(false)
    expect(rows[1]!.find('.inv-item__basis').text()).toContain('staff.invoices.confirmBasis')
    expect(rows[1]!.find('.inv-item__basis').text()).toContain('paid by bank transfer')
    expect(rows[2]!.find('.inv-item__requested').exists()).toBe(false)
    expect(rows[2]!.find('.inv-item__basis').exists()).toBe(false)
    wrapper.unmount()
  })

  it('reads only the open requests when their chip is pressed, and all again when released', async () => {
    listIs([])
    const wrapper = mount(StaffCryptoInvoicesView)
    await flushPromises()
    expect(fetchCryptoInvoices).toHaveBeenLastCalledWith(
      expect.objectContaining({ open_request: undefined }),
    )
    await wrapper.find('.inv-open-filter').trigger('click')
    await flushPromises()
    expect(fetchCryptoInvoices).toHaveBeenLastCalledWith(
      expect.objectContaining({ open_request: true, page: 1 }),
    )
    expect(wrapper.find('.inv-open-filter').attributes('aria-pressed')).toBe('true')
    await wrapper.find('.inv-open-filter').trigger('click')
    await flushPromises()
    expect(fetchCryptoInvoices).toHaveBeenLastCalledWith(
      expect.objectContaining({ open_request: undefined }),
    )
    wrapper.unmount()
  })

  it("opens with the open requests' filter when the address asks for it (the Home's counter)", async () => {
    routeQuery.value = { open_request: '1' }
    listIs([])
    const wrapper = mount(StaffCryptoInvoicesView)
    await flushPromises()
    expect(fetchCryptoInvoices).toHaveBeenCalledWith(expect.objectContaining({ open_request: true }))
    wrapper.unmount()
  })

  it('lists the notes oldest first with author and adds one, before or after Confirm', async () => {
    listIs([
      invoice('i1', {
        credited: true,
        credited_by: 'manual',
        notes: [
          { id: 'n1', text: 'asked for the statement', author_id: 'a', author_name: 'Ann Admin', created_at: '2026-10-25T09:00:00Z' },
          { id: 'n2', text: 'statement received', author_id: 'a', author_name: 'Ann Admin', created_at: '2026-10-25T10:00:00Z' },
        ],
      }),
    ])
    addCryptoInvoiceNote.mockResolvedValue({
      id: 'n3',
      text: 'balance checked',
      author_id: 'a',
      author_name: 'Ann Admin',
      created_at: '2026-10-25T11:00:00Z',
    })
    const wrapper = mount(StaffCryptoInvoicesView, { attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('.inv-item__notes').text()).toContain('(2)')
    await wrapper.find('.inv-item__notes').trigger('click')
    await flushPromises()

    const panel = () => document.body.querySelector('.ds-dialog__panel')!
    const texts = () =>
      Array.from(panel().querySelectorAll('.inv-note .ds-row__title')).map((n) => n.textContent)
    expect(texts()).toEqual(['asked for the statement', 'statement received'])
    expect(panel().querySelector('.inv-note .ds-row__meta')!.textContent).toContain('Ann Admin')

    const add = modalButton('staff.invoices.addNote')
    expect(add.disabled).toBe(true)
    const area = panel().querySelector('textarea') as HTMLTextAreaElement
    area.value = ' balance checked '
    area.dispatchEvent(new Event('input'))
    await flushPromises()
    expect(modalButton('staff.invoices.addNote').disabled).toBe(false)
    modalButton('staff.invoices.addNote').click()
    await flushPromises()
    expect(addCryptoInvoiceNote).toHaveBeenCalledWith('i1', { text: 'balance checked' })
    expect(texts()).toEqual(['asked for the statement', 'statement received', 'balance checked'])
    wrapper.unmount()
  })
})
