// =============================================================================
// StaffSupportView -- the rating in the list, its filter, the statistics tab (H41)
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    useRoute: () => ({ params: {}, query: {} }),
    useRouter: () => ({ push: vi.fn() }),
    RouterLink: defineComponent({
      props: { to: { type: [String, Object], required: true } },
      setup:
        (props, { slots }) =>
        () =>
          h('a', { href: JSON.stringify(props.to) }, slots.default?.()),
    }),
  }
})
vi.mock('@/api/support', async (importActual) => ({
  ...(await importActual<typeof import('@/api/support')>()),
  listStaffTickets: vi.fn(),
  getStaffSupportStats: vi.fn(),
}))

import * as api from '@/api/support'
import type { SupportTicketRow } from '@/api/support'
import StaffSupportView from './StaffSupportView.vue'

const list = vi.mocked(api.listStaffTickets)
const getStats = vi.mocked(api.getStaffSupportStats)

const ANN = { user_id: 'ann', first_name: 'Ann', last_name: null, email: null }

function row(over: Partial<SupportTicketRow> = {}): SupportTicketRow {
  return {
    id: 't1',
    topic: 'kyc',
    category: 'verification',
    status: 'resolved',
    created_at: '2026-10-25T12:00:00Z',
    status_changed_at: '2026-10-25T12:00:00Z',
    opener: { user_id: 'p', first_name: 'Pat', last_name: null, email: null },
    claimed_by: ANN,
    history_thread_id: null,
    resolved_by: ANN,
    rating: {
      stars: 4,
      comment: 'quick, thanks',
      comment_locale: 'en',
      rated_at: '2026-10-25T13:00:00Z',
      rated_resolver: ANN,
    },
    ...over,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  list.mockResolvedValue({ items: [row()], next_cursor: null })
})

describe('the ticket list -- ratings', () => {
  it('a row shows who resolved it and the rating with its comment', async () => {
    const wrapper = mount(StaffSupportView)
    await flushPromises()
    const text = wrapper.find('.ds-row').text()
    expect(text).toContain('staff.support.resolvedBy')
    expect(text).toContain('★★★★☆')
    expect(text).toContain('quick, thanks')
    wrapper.unmount()
  })

  it('an unrated, unresolved row says neither', async () => {
    list.mockResolvedValue({
      items: [row({ status: 'open', resolved_by: null, rating: null })],
      next_cursor: null,
    })
    const wrapper = mount(StaffSupportView)
    await flushPromises()
    const text = wrapper.find('.ds-row').text()
    expect(text).not.toContain('staff.support.resolvedBy')
    expect(text).not.toContain('★')
    wrapper.unmount()
  })

  it('the rating chips filter the list, "no rating" among them', async () => {
    const wrapper = mount(StaffSupportView)
    await flushPromises()
    const chip = (label: string) => wrapper.findAll('button').find((b) => b.text() === label)!
    await chip('★★★★★').trigger('click')
    await chip('staff.support.rating.none').trigger('click')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ rating: ['5', 'none'] }))
    await chip('★★★★★').trigger('click')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ rating: ['none'] }))
    await chip('staff.support.rating.none').trigger('click')
    await flushPromises()
    expect(list.mock.calls.at(-1)![0]!.rating).toBeUndefined()
    wrapper.unmount()
  })

  it('the statistics tab shows the statistics and reads no list', async () => {
    getStats.mockResolvedValue({
      period: { created_from: 'a', created_to: 'b' },
      categories: [],
      total: { tickets: 0, rated: 0, average: null, share_4_5: null },
      spam: { tickets: 0, live: 0, deleted: 0 },
      resolvers: [],
    })
    const wrapper = mount(StaffSupportView)
    await flushPromises()
    const reads = list.mock.calls.length
    const tab = wrapper.findAll('button').find((b) => b.text() === 'staff.support.tabStats')!
    await tab.trigger('click')
    await flushPromises()
    expect(getStats).toHaveBeenCalledTimes(1)
    expect(list.mock.calls.length).toBe(reads)
    expect(wrapper.find('.ds-rows').exists()).toBe(false)
    wrapper.unmount()
  })
})
