// =============================================================================
// the staff screens -- WHAT EACH ONE SHOWS FOR THE ANSWER IT IS GIVEN
// =============================================================================
//
// One mount per screen with its API mocked, asserting through the rendered text
// (translation keys here: the test catalogue is empty on purpose, see
// test-setup.ts). Axes: the screen's answer EMPTY, FULL, and FAILED -- a failed
// read must read as a failure, never as "nothing there".
// =============================================================================

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { config, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'

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
  fetchStaffPurchases: vi.fn(),
}))
vi.mock('@/api/products', () => ({ listProducts: vi.fn() }))
vi.mock('@/api/companies', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/companies')>()),
  getCompany: vi.fn(),
}))

import * as admin from '@/api/admin'
import * as companies from '@/api/companies'
import * as products from '@/api/products'
import { resetSharesPerOptionCache } from '@/composables/useSharesPerOption'
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
const cancelGift = vi.mocked(admin.cancelGift)
const fetchStaffPurchases = vi.mocked(admin.fetchStaffPurchases)
const listProducts = vi.mocked(products.listProducts)
const getCompany = vi.mocked(companies.getCompany)

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
    expect(wrapper.find('.ds-pager__item[aria-current="page"]').text()).toBe('1')
    expect(wrapper.findAll('.ds-pager__item').map((i) => i.text())).toContain('3')
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
    expect(wrapper.find('.ds-empty[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('.ds-rows').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('gifts', () => {
  // Project One has one offer and 25 parts in a lot; Project Two has two offers and 10.
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
  const TWO_A = {
    ...PRODUCT,
    id: 'prod-2a',
    company_id: 'c2',
    name: 'Small',
    company_name: 'Project Two',
  }
  const TWO_B = {
    ...PRODUCT,
    id: 'prod-2b',
    company_id: 'c2',
    name: 'Large',
    company_name: 'Project Two',
  }

  // The texts these tests read with their numbers; the rest resolve to their keys.
  function texts() {
    return createI18n({
      legacy: false,
      locale: 'en',
      missingWarn: false,
      fallbackWarn: false,
      messages: {
        en: {
          common: { close: 'Close' },
          staff: {
            gifts: {
              partsCount: '{n} parts',
              lots: 'Lots: {n}',
              partsNotWhole: 'lots of {per}: {below} or {above}',
              partsTooFew: 'lots of {per}: at least {above}',
            },
          },
        },
      },
    })
  }

  function mountGifts(options: Record<string, unknown> = {}) {
    return mount(StaffGiftsView, options)
  }

  function giftRow(id: string, status: string, kind = 'gift', created = '2026-10-23T10:00:00Z') {
    return {
      id,
      created_at: created,
      buyer_id: `buyer-${id}`,
      buyer_email: 'ada@example.com',
      buyer_name: 'Ada Lovelace',
      company_id: 'c1',
      company_name: 'Project One',
      product_id: 'prod-1',
      product_name: 'Package',
      units: 250,
      paid_cents: 0,
      kind,
      legal_basis: 'gift',
      status,
    }
  }

  function purchasesAre(waiting: unknown[], recent: unknown[]) {
    fetchStaffPurchases.mockImplementation(async (params) => {
      const items = params?.status === 'pending_acceptance' ? waiting : recent
      return { items, total: items.length, page: 1, per_page: 100 } as never
    })
  }

  function productsAre(items: unknown[]) {
    listProducts.mockResolvedValue({ items, total: items.length, page: 1, per_page: 100 } as never)
  }

  // The texts above stand in for the global catalogue while these tests run.
  let globalPlugins: typeof config.global.plugins = []
  beforeEach(() => {
    globalPlugins = config.global.plugins
    config.global.plugins = [texts()]
  })
  afterEach(() => {
    config.global.plugins = globalPlugins
  })

  beforeEach(() => {
    resetSharesPerOptionCache()
    getCompany.mockImplementation(
      async (id: string) => ({ shares_per_option: id === 'c2' ? 10 : 25 }) as never,
    )
  })

  it('lists the gifts from the purchases: waiting ones from the server filter, accepted ones picked out of the newest', async () => {
    productsAre([PRODUCT])
    purchasesAre(
      [giftRow('w1', 'pending_acceptance')],
      [
        giftRow('w1', 'pending_acceptance'),
        giftRow('a1', 'active', 'gift', '2026-10-22T10:00:00Z'),
        giftRow('p1', 'active', 'paid'),
      ],
    )
    const wrapper = mountGifts()
    await flushPromises()
    expect(fetchStaffPurchases).toHaveBeenCalledWith({
      status: 'pending_acceptance',
      per_page: 100,
    })
    // The waiting gift once, the accepted gift, and no paid purchase.
    expect(wrapper.findAll('.gifts__list .ds-row')).toHaveLength(2)
    // Only the waiting gift carries a cancel.
    expect(wrapper.findAll('.gifts__list .ds-button')).toHaveLength(1)
    wrapper.unmount()
  })

  it('shows each gift of the list in parts, never in lots', async () => {
    productsAre([PRODUCT])
    purchasesAre([giftRow('w1', 'pending_acceptance')], [giftRow('w1', 'pending_acceptance')])
    const wrapper = mountGifts()
    await flushPromises()
    const title = wrapper.find('.gifts__list .ds-row__title').text()
    // 250 lots of 25 parts.
    expect(title).toContain('6,250 parts')
    expect(title).not.toMatch(/— 250 parts/)
    wrapper.unmount()
  })

  it('shows the same list on a second visit (a reload does not lose it)', async () => {
    productsAre([PRODUCT])
    purchasesAre([giftRow('w1', 'pending_acceptance')], [giftRow('w1', 'pending_acceptance')])
    const first = mountGifts()
    await flushPromises()
    first.unmount()
    const second = mountGifts()
    await flushPromises()
    expect(second.findAll('.gifts__list .ds-row')).toHaveLength(1)
    second.unmount()
  })

  it('cancels a waiting gift and reads the list again', async () => {
    productsAre([PRODUCT])
    purchasesAre([giftRow('w1', 'pending_acceptance')], [giftRow('w1', 'pending_acceptance')])
    cancelGift.mockResolvedValue({} as never)
    const wrapper = mountGifts()
    await flushPromises()
    const before = fetchStaffPurchases.mock.calls.length
    await wrapper.find('.gifts__list .ds-button').trigger('click')
    await flushPromises()
    expect(cancelGift).toHaveBeenCalledWith('w1')
    expect(fetchStaffPurchases.mock.calls.length).toBeGreaterThan(before)
    wrapper.unmount()
  })

  it('says a failed read of the list is a failure, not an empty list', async () => {
    productsAre([PRODUCT])
    fetchStaffPurchases.mockRejectedValue(new Error('500'))
    const wrapper = mountGifts()
    await flushPromises()
    expect(wrapper.find('.gifts__list').text()).toContain('common.error')
    expect(wrapper.find('.gifts__list').text()).not.toContain('staff.gifts.listEmpty')
    wrapper.unmount()
  })

  it('chooses the only offer of a one-offer project by itself and hides the offer picker', async () => {
    productsAre([PRODUCT, TWO_A, TWO_B])
    purchasesAre([], [])
    const wrapper = mountGifts()
    await flushPromises()
    // One project picker, one entry per project.
    expect(wrapper.findAll('select')).toHaveLength(1)
    expect(wrapper.findAll('.gifts__project option:not([disabled])').map((o) => o.text())).toEqual([
      'Project One',
      'Project Two',
    ])
    await wrapper.find('.gifts__project select').setValue('c1')
    await flushPromises()
    expect(wrapper.find('.gifts__offer').exists()).toBe(false)
    // The read-only summary is there: the only offer is chosen.
    expect(wrapper.find('.gifts__sum').exists()).toBe(true)
    // 5 cents a lot over 25 parts.
    expect(wrapper.find('.gifts__part-price').text()).toBe('$0.002')
    wrapper.unmount()
  })

  it('asks for the offer when the project has several', async () => {
    productsAre([PRODUCT, TWO_A, TWO_B])
    purchasesAre([], [])
    const wrapper = mountGifts()
    await flushPromises()
    await wrapper.find('.gifts__project select').setValue('c2')
    await flushPromises()
    const offer = wrapper.find('.gifts__offer')
    expect(offer.exists()).toBe(true)
    expect(offer.findAll('option:not([disabled])').map((o) => o.text())).toEqual(['Small', 'Large'])
    // Nothing is summed until the offer is chosen.
    expect(wrapper.find('.gifts__sum').exists()).toBe(false)
    await offer.find('select').setValue('prod-2b')
    await flushPromises()
    expect(wrapper.find('.gifts__sum').exists()).toBe(true)
    // 5 cents a lot over 10 parts.
    expect(wrapper.find('.gifts__part-price').text()).toBe('$0.005')
    wrapper.unmount()
  })

  it('turns the parts into lots and shows the parts, the lots and the total', async () => {
    productsAre([PRODUCT])
    purchasesAre([], [])
    const wrapper = mountGifts()
    await flushPromises()
    await wrapper.find('.gifts__project select').setValue('c1')
    await flushPromises()
    await wrapper.find('input[inputmode="numeric"]').setValue('250')
    const sum = wrapper.find('.gifts__sum')
    expect(sum.text()).toContain('250')
    expect(sum.find('.gifts__lots').text()).toBe('Lots: 10')
    // 10 lots at 5 cents.
    expect(wrapper.find('.gifts__total').text()).toBe('$0.50')
    expect(wrapper.find('.ds-field__error').exists()).toBe(false)
    wrapper.unmount()
  })

  it('refuses parts that are not whole lots and names the two nearest valid counts', async () => {
    productsAre([PRODUCT])
    purchasesAre([], [])
    const wrapper = mountGifts()
    await flushPromises()
    await wrapper.find('.gifts__project select').setValue('c1')
    await flushPromises()
    const input = wrapper.find('input[inputmode="numeric"]')
    await input.setValue('260')
    expect(wrapper.text()).toContain('lots of 25: 250 or 275')
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeDefined()
    await input.setValue('10')
    expect(wrapper.text()).toContain('lots of 25: at least 25')
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('sends the recipient, the product and the parts as whole lots, and then lists the gift', async () => {
    productsAre([PRODUCT])
    purchasesAre([], [])
    grantGift.mockImplementation(async () => {
      // From now on the purchases hold the gift.
      purchasesAre([giftRow('g1', 'pending_acceptance')], [giftRow('g1', 'pending_acceptance')])
      return { id: 'g1' } as never
    })
    const wrapper = mountGifts({ attachTo: document.body })
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
    await wrapper.find('.gifts__project select').setValue('c1')
    await flushPromises()
    await wrapper.find('input[inputmode="numeric"]').setValue('250')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    // The confirmation: pressing the grant button in the modal sends it.
    const confirm = Array.from(document.body.querySelectorAll('.ds-dialog__panel button')).find(
      (b) => (b.textContent ?? '').includes('staff.gifts.grant'),
    ) as HTMLButtonElement
    confirm.click()
    await flushPromises()

    // 250 parts of 25 a lot: the server is sent 10 lots.
    expect(grantGift).toHaveBeenCalledWith({ user_id: 'u1', product_id: 'prod-1', units: 10 })
    // The list is read again from the purchases after the grant.
    expect(wrapper.find('.gifts__list').text()).toContain('Ada Lovelace')
    expect(wrapper.find('.gifts__list .ds-row__trail .ds-button').exists()).toBe(true)
    wrapper.unmount()
  })

  it('does not enable the grant button until the form is whole', async () => {
    productsAre([PRODUCT])
    purchasesAre([], [])
    const wrapper = mountGifts()
    await flushPromises()
    const submit = wrapper.find('button[type="submit"]')
    expect(submit.attributes('disabled')).toBeDefined()
    await wrapper.find('input[inputmode="numeric"]').setValue('not a number')
    expect(submit.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
