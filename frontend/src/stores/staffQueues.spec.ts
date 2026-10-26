// =============================================================================
// stores/staffQueues -- THE HOME'S COUNTERS: A FAILED READ IS AN ERROR, NEVER A ZERO
// =============================================================================
//
// Axes: a read that SUCCEEDS with zero (an empty queue), a read that FAILS (it
// must not look like that zero), a member WITHOUT the right to a queue (the
// queue is not read at all), and one failing read BESIDE reads that succeed
// (the others keep their numbers).
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import * as admin from '@/api/admin'
import * as support from '@/api/support'
import { QUEUES, queueAllowed, useStaffQueuesStore } from './staffQueues'
import type { StaffPermissionKey } from '@/composables/useStaffPermissions'

vi.mock('@/api/admin', () => ({
  fetchDashboardStats: vi.fn(),
  fetchAgentApplications: vi.fn(),
  fetchWithdrawalsStaff: vi.fn(),
}))
vi.mock('@/api/support', () => ({ listStaffTickets: vi.fn() }))

const fetchDashboardStats = vi.mocked(admin.fetchDashboardStats)
const fetchAgentApplications = vi.mocked(admin.fetchAgentApplications)
const fetchWithdrawalsStaff = vi.mocked(admin.fetchWithdrawalsStaff)
const listStaffTickets = vi.mocked(support.listStaffTickets)

const ALL = () => true
const only =
  (...held: StaffPermissionKey[]) =>
  (key: StaffPermissionKey) =>
    held.includes(key)

function stats(overrides: Record<string, number> = {}) {
  return {
    total_users: 7,
    users_by_role: {},
    pending_kyc_count: 3,
    active_avatar_sessions: 0,
    frozen_payments_count: 2,
    manual_topup_requests_count: 6,
    ...overrides,
  } as never
}

function mockAllOk() {
  fetchDashboardStats.mockResolvedValue(stats())
  fetchWithdrawalsStaff.mockResolvedValue({ items: [], total: 4, page: 1, per_page: 1 } as never)
  fetchAgentApplications.mockResolvedValue({ items: [], total: 5, page: 1, per_page: 1 } as never)
  // H40: open tickets; who took one is `claimed_by` (a person, or null).
  listStaffTickets.mockResolvedValue({
    items: [{ claimed_by: null }, { claimed_by: { user_id: 'op-1' } }, { claimed_by: null }],
    next_cursor: null,
  } as never)
}

describe('the staff Home counters', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    for (const fn of [
      fetchDashboardStats,
      fetchAgentApplications,
      fetchWithdrawalsStaff,
      listStaffTickets,
    ]) {
      fn.mockReset()
    }
  })

  it('counts every queue the member may work', async () => {
    mockAllOk()
    const store = useStaffQueuesStore()
    await store.loadAll(ALL)
    expect(store.queues.kyc).toMatchObject({ status: 'ready', count: 3 })
    expect(store.queues.topups).toMatchObject({ status: 'ready', count: 2 })
    expect(store.queues.withdrawals).toMatchObject({ status: 'ready', count: 4 })
    expect(store.queues.agentApps).toMatchObject({ status: 'ready', count: 5 })
    // Two of the three support requests nobody has taken.
    expect(store.queues.support).toMatchObject({ status: 'ready', count: 2, more: false })
    // The window read is of OPEN tickets: a closed one is nobody's work.
    expect(listStaffTickets).toHaveBeenCalledWith(expect.objectContaining({ status: 'open' }))
    expect(store.users).toMatchObject({ status: 'ready', count: 7 })
    expect(store.anyFailed).toBe(false)
  })

  it('keeps the users by role and the open avatar sessions of the same read', async () => {
    mockAllOk()
    fetchDashboardStats.mockResolvedValue({
      total_users: 7,
      users_by_role: { investor: 5, staff: 2, odd: 'x' },
      pending_kyc_count: 3,
      active_avatar_sessions: 2,
      frozen_payments_count: 2,
    } as never)
    const store = useStaffQueuesStore()
    await store.loadAll(ALL)
    // A value that is not a number is dropped, not drawn.
    expect(store.overview).toEqual({
      status: 'ready',
      byRole: { investor: 5, staff: 2 },
      avatarSessions: 2,
    })
  })

  it('shows a real zero as a zero (the read succeeded)', async () => {
    mockAllOk()
    fetchAgentApplications.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 1 } as never)
    const store = useStaffQueuesStore()
    await store.loadAll(ALL)
    expect(store.queues.agentApps).toMatchObject({ status: 'ready', count: 0 })
  })

  it('shows a failed read as an error and not as a zero', async () => {
    mockAllOk()
    fetchAgentApplications.mockRejectedValue(new Error('network'))
    const store = useStaffQueuesStore()
    await store.loadAll(ALL)
    expect(store.queues.agentApps.status).toBe('error')
    expect(store.anyFailed).toBe(true)
  })

  it('leaves the other counters standing when one read fails', async () => {
    mockAllOk()
    fetchWithdrawalsStaff.mockRejectedValue(new Error('500'))
    const store = useStaffQueuesStore()
    await store.loadAll(ALL)
    expect(store.queues.withdrawals.status).toBe('error')
    expect(store.queues.kyc).toMatchObject({ status: 'ready', count: 3 })
    expect(store.queues.support).toMatchObject({ status: 'ready', count: 2 })
  })

  it('marks both statistics-based queues and the user count when the statistics fail', async () => {
    mockAllOk()
    fetchDashboardStats.mockRejectedValue(new Error('down'))
    const store = useStaffQueuesStore()
    await store.loadAll(ALL)
    expect(store.queues.kyc.status).toBe('error')
    expect(store.queues.topups.status).toBe('error')
    expect(store.users.status).toBe('error')
  })

  it('does not read a queue the member has no right to', async () => {
    mockAllOk()
    const store = useStaffQueuesStore()
    // A member who may only decide identity checks: no payments, no applications.
    await store.loadAll(only('kyc_approve'))
    expect(fetchWithdrawalsStaff).not.toHaveBeenCalled()
    expect(fetchAgentApplications).not.toHaveBeenCalled()
    expect(listStaffTickets).toHaveBeenCalledTimes(1) // support is open to every member
    expect(store.queues.kyc).toMatchObject({ status: 'ready', count: 3 })
  })

  it('counts a floor ("N+") when the support list is longer than the page read', async () => {
    mockAllOk()
    listStaffTickets.mockResolvedValue({
      items: [{ claimed_by: null }],
      next_cursor: 'more',
    } as never)
    const store = useStaffQueuesStore()
    await store.loadAll(ALL)
    expect(store.queues.support).toMatchObject({ count: 1, more: true })
  })

  it("counts the clients' manual top-up requests for an administrator", async () => {
    mockAllOk()
    const store = useStaffQueuesStore()
    await store.loadAll(ALL, true)
    expect(store.queues.manualTopups).toMatchObject({ status: 'ready', count: 6, more: false })
  })

  it('leaves the manual top-up requests out for a member who is not an administrator', async () => {
    mockAllOk()
    const store = useStaffQueuesStore()
    await store.loadAll(ALL)
    expect(store.queues.manualTopups.status).toBe('loading')
    expect(QUEUES.filter((q) => queueAllowed(q, ALL, false)).map((q) => q.key)).not.toContain(
      'manualTopups',
    )
    expect(QUEUES.filter((q) => queueAllowed(q, ALL, true)).map((q) => q.key)).toContain(
      'manualTopups',
    )
  })

  it('opens the crypto invoices filtered to the open requests', () => {
    const spec = QUEUES.find((q) => q.key === 'manualTopups')!
    expect(spec.path).toBe('/staff/finance/invoices?open_request=1')
    expect(spec.permission).toBe('financial_operations')
  })

  it('shows the manual top-up counter as failed, not zero, when the statistics fail', async () => {
    mockAllOk()
    fetchDashboardStats.mockRejectedValue(new Error('down'))
    const store = useStaffQueuesStore()
    await store.loadAll(ALL, true)
    expect(store.queues.manualTopups.status).toBe('error')
  })
})
