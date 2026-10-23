// =============================================================================
// the staff screens -- WHAT EACH ONE SHOWS FOR THE ANSWER IT IS GIVEN
// =============================================================================
//
// One mount per screen with its API mocked, asserting through the rendered text
// (translation keys here: the test catalogue is empty on purpose, see
// test-setup.ts). Axes: the screen's answer EMPTY, FULL, and FAILED -- a failed
// read must read as a failure, never as "nothing there".
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/composables/safeNavigate', () => ({ safeNavigate: vi.fn() }))
vi.mock('@/api/admin', () => ({
  fetchPayments: vi.fn(),
  reversePayment: vi.fn(),
  fetchWithdrawalsStaff: vi.fn(),
  confirmWithdrawal: vi.fn(),
  rejectWithdrawal: vi.fn(),
  fetchAgentApplications: vi.fn(),
  approveAgentApplication: vi.fn(),
  rejectAgentApplication: vi.fn(),
  fetchConsistency: vi.fn(),
  fetchUsers: vi.fn(async () => ({ items: [], total: 0, page: 1, per_page: 8 })),
  grantGift: vi.fn(),
  cancelGift: vi.fn(),
}))
vi.mock('@/api/products', () => ({ listProducts: vi.fn() }))

import * as admin from '@/api/admin'
import * as products from '@/api/products'
import StaffAgentAppsView from './StaffAgentAppsView.vue'
import StaffGiftsView from './StaffGiftsView.vue'
import StaffPaymentsView from './StaffPaymentsView.vue'
import StaffReconciliationView from './StaffReconciliationView.vue'
import StaffWithdrawalsView from './StaffWithdrawalsView.vue'

const fetchPayments = vi.mocked(admin.fetchPayments)
const fetchWithdrawalsStaff = vi.mocked(admin.fetchWithdrawalsStaff)
const fetchAgentApplications = vi.mocked(admin.fetchAgentApplications)
const fetchConsistency = vi.mocked(admin.fetchConsistency)
const grantGift = vi.mocked(admin.grantGift)
const listProducts = vi.mocked(products.listProducts)

beforeEach(() => {
  setActivePinia(createPinia())
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('payments: the queue of top-ups in their hour', () => {
  const inAnHour = new Date(Date.now() + 40 * 60_000).toISOString()

  function payment(status: string, extra: Record<string, unknown> = {}) {
    return {
      id: `p-${status}`,
      amount_cents: 12_500,
      currency: 'usdt',
      payment_type: 'crypto',
      provider: 'provider-x',
      status,
      frozen_until: null,
      created_at: '2026-10-20T10:00:00Z',
      user_id: '12345678-aaaa-bbbb-cccc-1234567890ab',
      ...extra,
    }
  }

  it('lists a frozen top-up with its time left and offers to reverse it', async () => {
    fetchPayments.mockImplementation(async (params) => {
      const frozen = params?.status === 'frozen'
      return {
        items: frozen ? [payment('frozen', { frozen_until: inAnHour })] : [payment('confirmed')],
        total: 1,
        page: 1,
        per_page: 20,
      } as never
    })
    const wrapper = mount(StaffPaymentsView)
    await flushPromises()
    const queue = wrapper.find('.pay-queue')
    expect(queue.text()).toContain('125.00 USDT')
    // 40 minutes left, rounded up by the minute: the message carries the number.
    expect(queue.text()).toContain('staff.payments.queue.minutesLeft')
    expect(queue.find('.pay-item__reverse').exists()).toBe(true)
    wrapper.unmount()
  })

  it('says the queue is empty when nothing is in its hour', async () => {
    fetchPayments.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 20 } as never)
    const wrapper = mount(StaffPaymentsView)
    await flushPromises()
    expect(wrapper.find('.pay-queue').text()).toContain('staff.payments.queue.empty')
    wrapper.unmount()
  })

  it('shows a failed queue read as a failure, not as an empty queue', async () => {
    fetchPayments.mockImplementation(async (params) => {
      if (params?.status === 'frozen') throw new Error('network')
      return { items: [], total: 0, page: 1, per_page: 20 } as never
    })
    const wrapper = mount(StaffPaymentsView)
    await flushPromises()
    const queue = wrapper.find('.pay-queue')
    expect(queue.text()).toContain('staff.payments.queue.error')
    expect(queue.text()).not.toContain('staff.payments.queue.empty')
    wrapper.unmount()
  })

  it('offers the reversal for a confirmed payment too, and for no failed one', async () => {
    fetchPayments.mockImplementation(async (params) => {
      if (params?.status === 'frozen')
        return { items: [], total: 0, page: 1, per_page: 20 } as never
      return {
        items: [payment('confirmed'), payment('failed')],
        total: 2,
        page: 1,
        per_page: 20,
      } as never
    })
    const wrapper = mount(StaffPaymentsView)
    await flushPromises()
    const rows = wrapper.findAll('.pay-list .pay-item')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.find('.pay-item__reverse').exists()).toBe(true)
    expect(rows[1]!.find('.pay-item__reverse').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('withdrawals: where the money goes', () => {
  it('shows the network and the wallet as two lines and never the raw object', async () => {
    fetchWithdrawalsStaff.mockResolvedValue({
      items: [
        {
          id: 'w1',
          user_id: '12345678-aaaa-bbbb-cccc-1234567890ab',
          amount_cents: 5000,
          status: 'pending',
          created_at: '2026-10-20T10:00:00Z',
          rejection_reason: null,
          payout_details_snapshot: { wallet: 'TXyzWallet', network: 'TRC20' },
        },
      ],
      total: 1,
      page: 1,
      per_page: 20,
    } as never)
    const wrapper = mount(StaffWithdrawalsView)
    await flushPromises()
    const text = wrapper.find('.wd-item__payout').text()
    // The test catalogue has no label, so each label shows as its own key (tOrRaw).
    expect(text).toBe('networkTRC20walletTXyzWallet')
    expect(wrapper.text()).not.toContain('{')
    wrapper.unmount()
  })
})

describe('integrator applications: the paged queue with the applicant', () => {
  it('shows the name, the e-mail and the identity-check status of each applicant', async () => {
    fetchAgentApplications.mockResolvedValue({
      items: [
        {
          id: 'a1',
          user_id: 'u1',
          status: 'pending',
          created_at: '2026-10-20T10:00:00Z',
          applicant_name: 'Ada Lovelace',
          applicant_email: 'ada@example.com',
          applicant_kyc_status: 'approved',
        },
      ],
      total: 45,
      page: 1,
      per_page: 20,
    } as never)
    const wrapper = mount(StaffAgentAppsView)
    await flushPromises()
    expect(fetchAgentApplications).toHaveBeenCalledWith({ page: 1, per_page: 20 })
    const text = wrapper.text()
    expect(text).toContain('Ada Lovelace')
    expect(text).toContain('ada@example.com')
    // 45 applications at 20 a page: three pages.
    expect(wrapper.find('.apps-pagination__page').text()).toBe('1 / 3')
    wrapper.unmount()
  })

  it('shows a dash for an applicant without an e-mail (a Telegram account)', async () => {
    fetchAgentApplications.mockResolvedValue({
      items: [
        {
          id: 'a2',
          user_id: 'u2',
          status: 'pending',
          created_at: '2026-10-20T10:00:00Z',
          applicant_name: 'Grace',
          applicant_email: null,
          applicant_kyc_status: 'not_started',
        },
      ],
      total: 1,
      page: 1,
      per_page: 20,
    } as never)
    const wrapper = mount(StaffAgentAppsView)
    await flushPromises()
    expect(wrapper.find('.app-item__detail').text()).toContain('—')
    wrapper.unmount()
  })
})

describe('the money check', () => {
  it('puts the failed checks first', async () => {
    fetchConsistency.mockResolvedValue({
      overall_status: 'fail',
      total: 3,
      passed: 2,
      failed: 1,
      results: [
        { name: 'S-01', status: 'pass', severity: 'critical', details: { total: 0 } },
        {
          name: 'S-12',
          status: 'fail',
          severity: 'high',
          details: { gift_purchases_with_nonzero_paid: 2 },
        },
        { name: 'S-02', status: 'pass', severity: 'critical', details: null },
      ],
    } as never)
    const wrapper = mount(StaffReconciliationView)
    await flushPromises()
    const codes = wrapper.findAll('.recon__code').map((c) => c.text())
    expect(codes).toEqual(['S-12', 'S-01', 'S-02'])
    wrapper.unmount()
  })

  it('shows a failed read as an error', async () => {
    fetchConsistency.mockRejectedValue(new Error('500'))
    const wrapper = mount(StaffReconciliationView)
    await flushPromises()
    expect(wrapper.find('.recon__error').exists()).toBe(true)
    expect(wrapper.find('.recon__list').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('gifts', () => {
  const PRODUCT = {
    id: 'prod-1',
    company_id: 'c1',
    name: 'Package',
    description: null,
    package_size: 1000,
    price_per_unit_cents: 5,
    price_per_pack_cents: 5000,
    available_packages: 10,
    company_name: 'Project One',
  }

  it('sends the recipient, the product and the number of parts, and then lists the gift', async () => {
    listProducts.mockResolvedValue({ items: [PRODUCT], total: 1, page: 1, per_page: 100 } as never)
    grantGift.mockResolvedValue({
      id: 'g1',
      investor_id: 'u1',
      product_id: 'prod-1',
      company_id: 'c1',
      legal_basis: 'gift',
      units: 250,
      paid_cents: 0,
      price_per_unit_cents: 5,
      status: 'pending_acceptance',
      created_at: '2026-10-23T10:00:00Z',
    } as never)
    const wrapper = mount(StaffGiftsView, { attachTo: document.body })
    await flushPromises()

    // The recipient is chosen in the picker; stand in for its selection.
    const picker = wrapper.findComponent({ name: 'UserPicker' })
    picker.vm.$emit('update:modelValue', 'u1')
    picker.vm.$emit('select', {
      id: 'u1',
      role: 'investor',
      first_name: 'Ada',
      last_name: 'Lovelace',
      email: 'ada@example.com',
    })
    await wrapper.find('select').setValue('prod-1')
    await wrapper.find('input[inputmode="numeric"]').setValue('250')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    // The confirmation: pressing the grant button in the modal sends it.
    const confirm = Array.from(document.body.querySelectorAll('.c-modal-dialog button')).find((b) =>
      (b.textContent ?? '').includes('staff.gifts.grant'),
    ) as HTMLButtonElement
    confirm.click()
    await flushPromises()

    expect(grantGift).toHaveBeenCalledWith({ user_id: 'u1', product_id: 'prod-1', units: 250 })
    expect(wrapper.find('.gifts__list').text()).toContain('Ada Lovelace')
    expect(wrapper.find('.gifts__cancel').exists()).toBe(true)
    wrapper.unmount()
  })

  it('does not enable the grant button until the form is whole', async () => {
    listProducts.mockResolvedValue({ items: [PRODUCT], total: 1, page: 1, per_page: 100 } as never)
    const wrapper = mount(StaffGiftsView)
    await flushPromises()
    const submit = wrapper.find('button[type="submit"]')
    expect(submit.attributes('disabled')).toBeDefined()
    await wrapper.find('input[inputmode="numeric"]').setValue('not a number')
    expect(submit.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
