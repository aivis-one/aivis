// =============================================================================
// StaffSupportTicketView -- what a ticket's card offers, by its state (H40)
// =============================================================================

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const ID = '0b0b0b0b-0000-4000-8000-000000000001'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: ID }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/api/support', async (importActual) => ({
  ...(await importActual<typeof import('@/api/support')>()),
  getStaffTicket: vi.fn(),
  getStaffThreadMessages: vi.fn(),
  listStaffOperators: vi.fn(),
  claimStaffTicket: vi.fn(),
  reopenStaffTicket: vi.fn(),
}))

import * as api from '@/api/support'
import { ApiResponseError } from '@/api/client'
import type { SupportTicketRow } from '@/api/support'
import { useAuthStore } from '@/stores/auth'
import StaffSupportTicketView from './StaffSupportTicketView.vue'

const getTicket = vi.mocked(api.getStaffTicket)
const getFeed = vi.mocked(api.getStaffThreadMessages)
const operators = vi.mocked(api.listStaffOperators)
const claim = vi.mocked(api.claimStaffTicket)

const ME = { user_id: 'me', first_name: 'Sam', last_name: 'Staff', email: null }
const COLLEAGUE = { user_id: 'other', first_name: 'Kim', last_name: null, email: null }

function ticket(over: Partial<SupportTicketRow> = {}): SupportTicketRow {
  return {
    id: ID,
    topic: 'kyc',
    category: 'verification',
    status: 'open',
    created_at: '2026-10-25T12:00:00Z',
    status_changed_at: '2026-10-25T12:00:00Z',
    opener: { user_id: 'person', first_name: 'Pat', last_name: null, email: 'pat@example.com' },
    claimed_by: null,
    history_thread_id: null,
    resolved_by: null,
    rating: null,
    ...over,
  }
}

async function open(row: SupportTicketRow) {
  getTicket.mockResolvedValue(row)
  getFeed.mockResolvedValue({ items: [], next_cursor: null })
  operators.mockResolvedValue({ items: [ME, COLLEAGUE], next_cursor: null })
  const wrapper = mount(StaffSupportTicketView)
  await flushPromises()
  return wrapper
}

function buttons(wrapper: ReturnType<typeof mount>): string[] {
  return wrapper.findAll('button').map((b) => b.text())
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  const auth = useAuthStore()
  auth.user = { id: 'me', role: 'staff' } as unknown as typeof auth.user
})

describe('the ticket card', () => {
  it('an open ticket nobody took: take it, close it, hand it over -- no composer', async () => {
    const wrapper = await open(ticket())
    const labels = buttons(wrapper)
    expect(labels).toContain('staff.support.claim')
    expect(labels).not.toContain('staff.support.release')
    expect(labels).not.toContain('staff.support.reopen')
    expect(labels).toEqual(
      expect.arrayContaining(['staff.support.close.spam', 'staff.support.assign']),
    )
    expect(wrapper.find('textarea').exists()).toBe(false)
    wrapper.unmount()
  })

  it('an open ticket I took: reply, give it back -- not take it again', async () => {
    const wrapper = await open(ticket({ claimed_by: ME }))
    const labels = buttons(wrapper)
    expect(labels).toContain('staff.support.release')
    expect(labels).not.toContain('staff.support.claim')
    expect(wrapper.find('textarea').exists()).toBe(true)
    wrapper.unmount()
  })

  it("a colleague's open ticket: read, hand over, close -- no reply, no taking", async () => {
    const wrapper = await open(ticket({ claimed_by: COLLEAGUE }))
    const labels = buttons(wrapper)
    expect(labels).not.toContain('staff.support.claim')
    expect(labels).not.toContain('staff.support.release')
    expect(labels).toContain('staff.support.assign')
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.text()).toContain('staff.support.foreignHint')
    wrapper.unmount()
  })

  it.each(['resolved', 'rejected', 'duplicate', 'spam'] as const)(
    'a %s ticket offers only the way back to work',
    async (status) => {
      const wrapper = await open(ticket({ status, claimed_by: ME }))
      const labels = buttons(wrapper)
      expect(labels).toContain('staff.support.reopen')
      expect(labels.some((l) => l.startsWith('staff.support.close.'))).toBe(false)
      expect(labels).not.toContain('staff.support.assign')
      expect(wrapper.find('textarea').exists()).toBe(false)
      wrapper.unmount()
    },
  )

  it('the operators to hand over to are everyone but the one who has it', async () => {
    const wrapper = await open(ticket({ claimed_by: COLLEAGUE }))
    const options = wrapper.findAll('option').map((o) => o.attributes('value'))
    expect(options).toContain('me')
    expect(options).not.toContain('other')
    wrapper.unmount()
  })

  it("a colleague's claim that won says so, in the operator's words", async () => {
    claim.mockRejectedValue(new ApiResponseError(409, 'taken'))
    const wrapper = await open(ticket())
    const take = wrapper.findAll('button').find((b) => b.text() === 'staff.support.claim')!
    await take.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('staff.support.claimConflict')
    wrapper.unmount()
  })

  it('a ticket that is not there is said to be gone', async () => {
    getTicket.mockRejectedValue(new ApiResponseError(404, 'Ticket not found'))
    const wrapper = mount(StaffSupportTicketView)
    await flushPromises()
    expect(wrapper.text()).toContain('staff.support.ticketGone')
    expect(getFeed).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it("the person's history swaps in read-only, and back", async () => {
    const wrapper = await open(ticket({ claimed_by: ME, history_thread_id: 'hist-1' }))
    expect(getFeed).toHaveBeenLastCalledWith(ID)
    const toggle = wrapper.findAll('button').find((b) => b.text() === 'staff.support.history')!
    await toggle.trigger('click')
    await flushPromises()
    expect(getFeed).toHaveBeenLastCalledWith('hist-1')
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(wrapper.text()).toContain('staff.support.historyHint')
    const back = wrapper.findAll('button').find((b) => b.text() === 'staff.support.backToTicket')!
    await back.trigger('click')
    await flushPromises()
    expect(getFeed).toHaveBeenLastCalledWith(ID)
    expect(wrapper.find('textarea').exists()).toBe(true)
    wrapper.unmount()
  })

  it('a rated ticket shows the stars, the comment as written with its language, and whom', async () => {
    const wrapper = await open(
      ticket({
        status: 'resolved',
        claimed_by: ME,
        resolved_by: COLLEAGUE,
        rating: {
          stars: 2,
          comment: 'долго',
          comment_locale: 'ru',
          rated_at: '2026-10-25T13:00:00Z',
          rated_resolver: COLLEAGUE,
        },
      }),
    )
    const rating = wrapper.find('.stck__rating')
    expect(rating.text()).toContain('★★☆☆☆')
    expect(rating.find('blockquote').text()).toBe('долго')
    expect(rating.find('blockquote').attributes('lang')).toBe('ru')
    expect(rating.text()).toContain('staff.support.rating.commentLocale')
    expect(rating.text()).toContain('staff.support.rating.about')
    expect(wrapper.text()).toContain('staff.support.resolver')
    expect(wrapper.text()).not.toContain('staff.support.lastResolver')
    wrapper.unmount()
  })

  it('closed another way since, the resolver reads as the last one', async () => {
    const wrapper = await open(ticket({ status: 'rejected', resolved_by: COLLEAGUE }))
    expect(wrapper.text()).toContain('staff.support.lastResolver')
    expect(wrapper.find('.stck__rating').exists()).toBe(false)
    wrapper.unmount()
  })
})
