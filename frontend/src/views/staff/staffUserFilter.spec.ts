// =============================================================================
// Finance lists narrowed to one person -- the address names the person, the
// picker chooses one, and the server is asked with ?user_id
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/admin', () => ({
  fetchPayments: vi.fn(),
  reversePayment: vi.fn(),
  fetchWithdrawalsStaff: vi.fn(),
  confirmWithdrawal: vi.fn(),
  rejectWithdrawal: vi.fn(),
  fetchUsers: vi.fn(async () => ({ items: [], total: 0, page: 1, per_page: 8 })),
  fetchUserDetail: vi.fn(),
}))

import * as admin from '@/api/admin'
import StaffPaymentsView from './StaffPaymentsView.vue'
import StaffWithdrawalsView from './StaffWithdrawalsView.vue'
import { searchForUser, userFromSearch } from '@/composables/useUrlUserFilter'

const fetchPayments = vi.mocked(admin.fetchPayments)
const fetchWithdrawalsStaff = vi.mocked(admin.fetchWithdrawalsStaff)
const fetchUserDetail = vi.mocked(admin.fetchUserDetail)

const EMPTY = { items: [], total: 0, page: 1, per_page: 20 }

beforeEach(() => {
  setActivePinia(createPinia())
  document.body.innerHTML = ''
  vi.clearAllMocks()
  window.history.replaceState({}, '', '/staff/finance/payments')
  fetchPayments.mockResolvedValue(EMPTY as never)
  fetchWithdrawalsStaff.mockResolvedValue(EMPTY as never)
  fetchUserDetail.mockResolvedValue({
    id: 'u-7',
    role: 'investor',
    is_active: true,
    kyc_status: 'approved',
    email: 'ada@example.com',
    profile: { first_name: 'Ada', last_name: 'Lovelace' },
    created_at: '2026-10-01T00:00:00Z',
  } as never)
})

describe('the address helpers', () => {
  it('reads the parameter and writes it back with the others kept', () => {
    expect(userFromSearch('?page=2&user_id=u-7', 'user_id')).toBe('u-7')
    expect(userFromSearch('?page=2', 'user_id')).toBe('')
    expect(searchForUser('?page=2', 'u-7', 'user_id')).toBe('?page=2&user_id=u-7')
    expect(searchForUser('?page=2&user_id=u-7', '', 'user_id')).toBe('?page=2')
  })
})

describe('payments of one person', () => {
  it('asks for every payment when no one is named', async () => {
    const wrapper = mount(StaffPaymentsView)
    await flushPromises()
    expect(fetchPayments).toHaveBeenCalledWith(expect.objectContaining({ user_id: undefined }))
    wrapper.unmount()
  })

  it('is opened on an address that names the person: both the queue and the list ask for them', async () => {
    window.history.replaceState({}, '', '/staff/finance/payments?user_id=u-7')
    const wrapper = mount(StaffPaymentsView)
    await flushPromises()
    const calls = fetchPayments.mock.calls.map((c) => c[0])
    expect(calls.length).toBeGreaterThanOrEqual(2)
    for (const params of calls) expect(params?.user_id).toBe('u-7')
    // The person is shown as a chip, read from the user card.
    expect(fetchUserDetail).toHaveBeenCalledWith('u-7')
    expect(wrapper.text()).toContain('Ada Lovelace')
    wrapper.unmount()
  })

  it('a person chosen in the picker narrows the list and is written into the address', async () => {
    const wrapper = mount(StaffPaymentsView)
    await flushPromises()
    wrapper.findComponent({ name: 'UserPicker' }).vm.$emit('update:modelValue', 'u-9')
    await flushPromises()
    expect(fetchPayments).toHaveBeenLastCalledWith(
      expect.objectContaining({ user_id: 'u-9', page: 1 }),
    )
    expect(window.location.search).toContain('user_id=u-9')
    wrapper.unmount()
  })
})

describe('withdrawals of one person', () => {
  it('is opened on an address that names the person', async () => {
    window.history.replaceState({}, '', '/staff/finance/withdrawals?user_id=u-7')
    const wrapper = mount(StaffWithdrawalsView)
    await flushPromises()
    expect(fetchWithdrawalsStaff).toHaveBeenCalledWith(expect.objectContaining({ user_id: 'u-7' }))
    wrapper.unmount()
  })

  it('a person chosen in the picker narrows the list', async () => {
    const wrapper = mount(StaffWithdrawalsView)
    await flushPromises()
    wrapper.findComponent({ name: 'UserPicker' }).vm.$emit('update:modelValue', 'u-9')
    await flushPromises()
    expect(fetchWithdrawalsStaff).toHaveBeenLastCalledWith(
      expect.objectContaining({ user_id: 'u-9', page: 1 }),
    )
    wrapper.unmount()
  })
})
