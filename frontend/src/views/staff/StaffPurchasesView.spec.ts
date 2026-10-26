// =============================================================================
// Finance > Purchases -- the read-only list, its paging and filters, and the
// Cancel of a gift that its recipient has not accepted yet
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/admin', () => ({
  fetchStaffPurchases: vi.fn(),
  cancelGift: vi.fn(),
  reversePurchase: vi.fn(),
  fetchUsers: vi.fn(),
}))
vi.mock('@/api/products', () => ({ listProducts: vi.fn() }))
vi.mock('@/api/staff-companies', () => ({ fetchStaffCompanies: vi.fn() }))

import { ApiResponseError } from '@/api/client'
import * as admin from '@/api/admin'
import * as products from '@/api/products'
import * as staffCompanies from '@/api/staff-companies'
import { useAuthStore } from '@/stores/auth'
import { PERMISSION_KEYS } from '@/utils/staffRights'
import StaffPurchasesView from './StaffPurchasesView.vue'

const fetchStaffPurchases = vi.mocked(admin.fetchStaffPurchases)
const cancelGift = vi.mocked(admin.cancelGift)
const listProducts = vi.mocked(products.listProducts)
const fetchStaffCompanies = vi.mocked(staffCompanies.fetchStaffCompanies)

function signInAs(held: readonly string[]): void {
  const auth = useAuthStore()
  auth.user = {
    id: 's1',
    role: 'staff',
    email: 'staff@example.com',
    language: 'en',
    profile: { first_name: 'Sam', last_name: 'Staff' },
    staff_profile: {
      id: 'p1',
      is_active: true,
      permissions: Object.fromEntries(PERMISSION_KEYS.map((key) => [key, held.includes(key)])),
    },
  } as unknown as typeof auth.user
}

function row(id: string, kind: string, status: string, buyer = 'Ada Lovelace') {
  return {
    id,
    created_at: '2026-10-20T10:00:00Z',
    buyer_id: `buyer-${id}`,
    buyer_email: 'ada@example.com',
    buyer_name: buyer,
    company_id: 'proj-1',
    company_name: 'Project One',
    product_id: 'prod-1',
    product_name: 'Starter',
    units: 250,
    paid_cents: kind === 'paid' ? 125000 : 0,
    kind,
    legal_basis: kind === 'paid' ? 'sale' : 'gift',
    status,
  }
}

function answer(items: ReturnType<typeof row>[], total = items.length, page = 1) {
  fetchStaffPurchases.mockResolvedValue({ items, total, page, per_page: 20 } as never)
}

beforeEach(() => {
  setActivePinia(createPinia())
  document.body.innerHTML = ''
  vi.clearAllMocks()
  fetchStaffCompanies.mockResolvedValue({
    items: [{ id: 'proj-1', name: 'Project One' }],
    total: 1,
    page: 1,
    per_page: 100,
  } as never)
  listProducts.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 100 } as never)
})

describe('the purchases list', () => {
  it('reads the first page and shows date, buyer, project, product, parts, amount, type and status', async () => {
    answer([row('a', 'paid', 'active'), row('b', 'gift', 'pending_acceptance')])
    signInAs(['financial_operations'])
    const wrapper = mount(StaffPurchasesView)
    await flushPromises()
    expect(fetchStaffPurchases).toHaveBeenCalledWith({
      status: undefined,
      company_id: undefined,
      buyer_id: undefined,
      page: 1,
      per_page: 20,
    })
    const text = wrapper.text()
    expect(text).toContain('Ada Lovelace')
    expect(text).toContain('Project One')
    expect(text).toContain('Starter')
    // The test catalogue is empty, so a word falls back to its raw token.
    expect(text).toContain('paid')
    expect(text).toContain('gift')
    expect(text).toContain('pending_acceptance')
    expect(text).toContain('1250.00')
    wrapper.unmount()
  })

  it('has no contract upload', async () => {
    answer([row('a', 'paid', 'active')])
    signInAs(['financial_operations'])
    const wrapper = mount(StaffPurchasesView)
    await flushPromises()
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('pages: the next page asks for page 2', async () => {
    answer([row('a', 'paid', 'active')], 45)
    signInAs(['financial_operations'])
    const wrapper = mount(StaffPurchasesView)
    await flushPromises()
    // 45 purchases at 20 a page: three pages, the first current.
    const items = wrapper.findAll('.ds-pager__item')
    expect(wrapper.find('.ds-pager__item[aria-current="page"]').text()).toBe('1')
    expect(items.map((i) => i.text())).toContain('3')
    const next = items[items.length - 1]!
    await next.trigger('click')
    await flushPromises()
    expect(fetchStaffPurchases).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2, per_page: 20 }),
    )
    wrapper.unmount()
  })

  it('a filter is sent to the server and starts again from the first page', async () => {
    answer([row('a', 'paid', 'active')], 45)
    signInAs(['financial_operations', 'company_manage'])
    const wrapper = mount(StaffPurchasesView)
    await flushPromises()
    const pagerItems = wrapper.findAll('.ds-pager__item')
    await pagerItems[pagerItems.length - 1]!.trigger('click')
    await flushPromises()
    const selects = wrapper.findAll('select')
    // status, then project
    await selects[0]!.setValue('pending_acceptance')
    await flushPromises()
    expect(fetchStaffPurchases).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'pending_acceptance', page: 1 }),
    )
    await selects[1]!.setValue('proj-1')
    await flushPromises()
    expect(fetchStaffPurchases).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'pending_acceptance', company_id: 'proj-1', page: 1 }),
    )
    wrapper.unmount()
  })

  it('a buyer chosen in the picker is sent as buyer_id', async () => {
    answer([row('a', 'paid', 'active')])
    signInAs(['financial_operations'])
    const wrapper = mount(StaffPurchasesView)
    await flushPromises()
    wrapper.findComponent({ name: 'UserPicker' }).vm.$emit('update:modelValue', 'buyer-7')
    await flushPromises()
    expect(fetchStaffPurchases).toHaveBeenLastCalledWith(
      expect.objectContaining({ buyer_id: 'buyer-7', page: 1 }),
    )
    wrapper.unmount()
  })

  it('shows an empty answer as empty and a failed read as a failure', async () => {
    answer([], 0)
    signInAs(['financial_operations'])
    const empty = mount(StaffPurchasesView)
    await flushPromises()
    expect(empty.text()).toContain('staff.purchases.empty')
    empty.unmount()

    fetchStaffPurchases.mockRejectedValue(new Error('500'))
    const failed = mount(StaffPurchasesView)
    await flushPromises()
    expect(failed.text()).toContain('common.error')
    expect(failed.text()).not.toContain('staff.purchases.empty')
    failed.unmount()
  })
})

describe('the cancel of a gift not yet accepted', () => {
  it('is on a pending gift row only, after a reload too', async () => {
    answer([
      row('paid', 'paid', 'active'),
      row('pending', 'gift', 'pending_acceptance'),
      row('accepted', 'gift', 'active'),
      row('bonus', 'bonus', 'active'),
      row('cancelled', 'gift', 'cancelled'),
    ])
    signInAs(['financial_operations'])
    const wrapper = mount(StaffPurchasesView)
    await flushPromises()
    const cancels = wrapper.findAll('.purch__cancel')
    expect(cancels).toHaveLength(1)
    expect(cancels[0]!.element.closest('.purch__row')!.textContent).toContain('pending_acceptance')
    wrapper.unmount()
  })

  it('cancels through the gift endpoint and reads the list again', async () => {
    answer([row('pending', 'gift', 'pending_acceptance')])
    cancelGift.mockResolvedValue({} as never)
    signInAs(['financial_operations'])
    const wrapper = mount(StaffPurchasesView)
    await flushPromises()
    await wrapper.find('.purch__cancel').trigger('click')
    await flushPromises()
    expect(cancelGift).toHaveBeenCalledWith('pending')
    expect(fetchStaffPurchases).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('is offered to a member with financial_operations who is not the administrator', async () => {
    answer([row('pending', 'gift', 'pending_acceptance')])
    signInAs(['financial_operations'])
    const wrapper = mount(StaffPurchasesView)
    await flushPromises()
    expect(wrapper.find('.purch__cancel').exists()).toBe(true)
    wrapper.unmount()
  })

  it('is not offered to a member without financial_operations', async () => {
    answer([row('pending', 'gift', 'pending_acceptance')])
    signInAs(['payment_review'])
    const wrapper = mount(StaffPurchasesView)
    await flushPromises()
    expect(wrapper.find('.purch__cancel').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('the reverse of an active purchase', () => {
  const reversePurchase = vi.mocked(admin.reversePurchase)

  function dialogButton(label: string): HTMLButtonElement {
    const buttons = Array.from(document.body.querySelectorAll('.ds-dialog__panel button'))
    return buttons.find((b) => b.textContent?.includes(label)) as HTMLButtonElement
  }

  it('is on active rows only, and only for a member who may review payments', async () => {
    answer([
      row('paid', 'paid', 'active'),
      row('pending', 'gift', 'pending_acceptance'),
      row('gone', 'paid', 'reversed'),
    ])
    signInAs(['financial_operations', 'payment_review'])
    const wrapper = mount(StaffPurchasesView)
    await flushPromises()
    const buttons = wrapper.findAll('.purch__reverse')
    expect(buttons).toHaveLength(1)
    expect(buttons[0]!.element.closest('.purch__row')!.textContent).toContain('1250.00')
    wrapper.unmount()

    signInAs(['financial_operations'])
    const plain = mount(StaffPurchasesView)
    await flushPromises()
    expect(plain.find('.purch__reverse').exists()).toBe(false)
    plain.unmount()
  })

  it('is not offered on an installment tranche', async () => {
    answer([{ ...row('tranche', 'installment', 'active'), legal_basis: 'installment_tranche' }])
    signInAs(['financial_operations', 'payment_review'])
    const wrapper = mount(StaffPurchasesView)
    await flushPromises()
    expect(wrapper.find('.purch__reverse').exists()).toBe(false)
    wrapper.unmount()
  })

  it('refuses an empty reason and sends nothing', async () => {
    answer([row('paid', 'paid', 'active')])
    signInAs(['financial_operations', 'payment_review'])
    const wrapper = mount(StaffPurchasesView, { attachTo: document.body })
    await flushPromises()
    await wrapper.find('.purch__reverse').trigger('click')
    dialogButton('staff.purchases.reverse').click()
    await flushPromises()
    expect(reversePurchase).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('staff.purchases.reverseReasonRequired')
    wrapper.unmount()
  })

  it('sends the reason, then reads the list again', async () => {
    answer([row('paid', 'paid', 'active')])
    reversePurchase.mockResolvedValue({} as never)
    signInAs(['financial_operations', 'payment_review'])
    const wrapper = mount(StaffPurchasesView, { attachTo: document.body })
    await flushPromises()
    await wrapper.find('.purch__reverse').trigger('click')
    const input = document.body.querySelector('.ds-dialog__panel input') as HTMLInputElement
    input.value = 'duplicate payment'
    input.dispatchEvent(new Event('input'))
    dialogButton('staff.purchases.reverse').click()
    await flushPromises()
    expect(reversePurchase).toHaveBeenCalledWith('paid', { reason: 'duplicate payment' })
    expect(fetchStaffPurchases).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('shows the server reason when the reverse fails, and keeps the dialog open', async () => {
    answer([row('paid', 'paid', 'active')])
    const err = new ApiResponseError(409, 'Purchase is already reversed')
    reversePurchase.mockRejectedValue(err)
    signInAs(['financial_operations', 'payment_review'])
    const wrapper = mount(StaffPurchasesView, { attachTo: document.body })
    await flushPromises()
    await wrapper.find('.purch__reverse').trigger('click')
    const input = document.body.querySelector('.ds-dialog__panel input') as HTMLInputElement
    input.value = 'x'
    input.dispatchEvent(new Event('input'))
    dialogButton('staff.purchases.reverse').click()
    await flushPromises()
    expect(document.body.textContent).toContain('Purchase is already reversed')
    expect(document.body.querySelector('.ds-dialog__panel')).not.toBeNull()
    wrapper.unmount()
  })
})
