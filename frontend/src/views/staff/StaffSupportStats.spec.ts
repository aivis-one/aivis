// =============================================================================
// StaffSupportStats -- the statistics tab (H41)
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/support', async (importActual) => ({
  ...(await importActual<typeof import('@/api/support')>()),
  getStaffSupportStats: vi.fn(),
}))

import * as api from '@/api/support'
import type { SupportStatsResponse } from '@/api/support'
import StaffSupportStats from './StaffSupportStats.vue'

const getStats = vi.mocked(api.getStaffSupportStats)

const NONE = { rated: 0, average: null, share_4_5: null }

function stats(): SupportStatsResponse {
  return {
    period: { created_from: 'a', created_to: 'b' },
    categories: api.SUPPORT_CATEGORIES.map((category) =>
      category === 'verification'
        ? { category, tickets: 3, rated: 2, average: 4.5, share_4_5: 1 }
        : { category, tickets: 0, ...NONE },
    ),
    total: { tickets: 3, rated: 2, average: 4.5, share_4_5: 1 },
    spam: { tickets: 4, live: 1, deleted: 3 },
    resolvers: [
      {
        operator: { user_id: 'op', first_name: 'Ann', last_name: null, email: null },
        rated: 2,
        average: 4.5,
        share_4_5: 1,
      },
    ],
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('the statistics', () => {
  it("opens on today: from this browser's midnight to the next", async () => {
    getStats.mockResolvedValue(stats())
    const wrapper = mount(StaffSupportStats)
    await flushPromises()
    const [from, to] = getStats.mock.calls[0]
    const start = new Date(from)
    const end = new Date(to)
    const now = new Date()
    expect([start.getDate(), start.getHours(), start.getMinutes()]).toEqual([now.getDate(), 0, 0])
    expect(end.getTime() - start.getTime()).toBeGreaterThanOrEqual(23 * 3600 * 1000)
    wrapper.unmount()
  })

  it('shows every category, nobody-rated as a dash, the total, spam and operators', async () => {
    getStats.mockResolvedValue(stats())
    const wrapper = mount(StaffSupportStats)
    await flushPromises()
    const rows = wrapper.findAll('tbody')[0].findAll('tr')
    expect(rows).toHaveLength(6)
    const verification = rows.find((r) => r.text().includes('categories.verification'))!
    expect(verification.findAll('td').map((c) => c.text())).toEqual(['3', '2', '4.5', '100%'])
    const purchases = rows.find((r) => r.text().includes('categories.purchases'))!
    expect(purchases.findAll('td').map((c) => c.text())).toEqual([
      '0',
      '0',
      'staff.support.stats.noValue',
      'staff.support.stats.noValue',
    ])
    expect(wrapper.find('tfoot').text()).toContain('3')
    expect(wrapper.text()).toContain('staff.support.stats.spam')
    expect(wrapper.text()).toContain('staff.support.stats.spamDeleted')
    expect(wrapper.text()).toContain('Ann')
    wrapper.unmount()
  })

  it('a last day before the first asks nothing and says why', async () => {
    getStats.mockResolvedValue(stats())
    const wrapper = mount(StaffSupportStats)
    await flushPromises()
    const [from, to] = wrapper.findAll('input')
    await from.setValue('2026-10-25')
    await to.setValue('2026-10-24')
    await flushPromises()
    expect(wrapper.text()).toContain('staff.support.stats.badPeriod')
    expect(getStats).toHaveBeenCalledTimes(1) // only the first, today's
    wrapper.unmount()
  })

  it('a period of several days is asked as one', async () => {
    getStats.mockResolvedValue(stats())
    const wrapper = mount(StaffSupportStats)
    await flushPromises()
    const [from, to] = wrapper.findAll('input')
    await from.setValue('2026-10-01')
    await to.setValue('2026-10-03')
    await flushPromises()
    const [start, end] = getStats.mock.calls.at(-1)!
    expect(new Date(start).getDate()).toBe(1)
    expect(new Date(end).getDate()).toBe(4) // the midnight after the last day
    wrapper.unmount()
  })
})
