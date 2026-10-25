// =============================================================================
// stores/support -- ONE PRESS OF SEND, ONE Idempotency-Key (H23 P-112)
// =============================================================================
//
// comms stores a message once per key. The store mints the key when the
// person presses send and keeps it with the draft until comms confirms,
// so a retry after a failure or a timeout goes out under the SAME key and
// comms answers with the message it already has. A new key per HTTP
// attempt would store a second message and ping a second time.
// =============================================================================

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/support', () => ({
  sendSupportMessage: vi.fn(),
  replyToStaffThread: vi.fn(),
  createSupportTicket: vi.fn(),
  listStaffTickets: vi.fn(),
  getStaffTicket: vi.fn(),
  claimStaffTicket: vi.fn(),
  getSupportUnread: vi.fn(),
  markSupportRead: vi.fn(),
}))

import {
  claimStaffTicket,
  createSupportTicket,
  getStaffTicket,
  getSupportUnread,
  listStaffTickets,
  markSupportRead,
  replyToStaffThread,
  sendSupportMessage,
} from '@/api/support'
import type { SupportTicketRow } from '@/api/support'
import { useSupportStore } from './support'

const send = vi.mocked(sendSupportMessage)
const reply = vi.mocked(replyToStaffThread)
const MESSAGE = { id: 'm1', thread_id: 't1', sender: 'u1', body: 'hi', created_at: null }

function keysOf(mock: typeof send | typeof reply, keyIndex: number): string[] {
  return mock.mock.calls.map((call) => call[keyIndex] as string)
}

describe('support store -- the Idempotency-Key of a message', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    send.mockReset()
    reply.mockReset()
  })

  it('reuses the key when the same text is retried after a failure', async () => {
    const store = useSupportStore()
    send.mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce(MESSAGE)

    await store.sendMessage('hi')
    await store.sendMessage('hi')

    const keys = keysOf(send, 1)
    expect(keys).toHaveLength(2)
    expect(keys[0]).toBeTruthy()
    expect(keys[1]).toBe(keys[0])
  })

  it('mints a new key for another text, and after a confirmed send', async () => {
    const store = useSupportStore()
    send.mockRejectedValueOnce(new Error('timeout')).mockResolvedValue(MESSAGE)

    await store.sendMessage('hi')
    await store.sendMessage('hello') // edited after the failure: another message
    await store.sendMessage('hello') // confirmed above: a new message

    const keys = keysOf(send, 1)
    expect(new Set(keys).size).toBe(3)
  })

  it('does not send twice for a press while the first is in flight', async () => {
    const store = useSupportStore()
    let release: (value: typeof MESSAGE) => void = () => {}
    send.mockReturnValueOnce(new Promise((resolve) => (release = resolve)))

    const first = store.sendMessage('hi')
    await store.sendMessage('hi')
    release(MESSAGE)
    await first

    expect(send).toHaveBeenCalledTimes(1)
  })

  it('keeps one pending key per thread on the operator side', async () => {
    const store = useSupportStore()
    reply.mockRejectedValueOnce(new Error('timeout')).mockResolvedValue(MESSAGE)

    await store.replyToThread('t1', 'on it')
    await store.replyToThread('t1', 'on it')

    const keys = keysOf(reply, 2)
    expect(keys[1]).toBe(keys[0])
  })
})

// -----------------------------------------------------------------------------
// H40: the form, the staff list and card, the badge
// -----------------------------------------------------------------------------

const create = vi.mocked(createSupportTicket)
const list = vi.mocked(listStaffTickets)
const card = vi.mocked(getStaffTicket)
const claim = vi.mocked(claimStaffTicket)
const unread = vi.mocked(getSupportUnread)
const markRead = vi.mocked(markSupportRead)

function row(id: string, over: Partial<SupportTicketRow> = {}): SupportTicketRow {
  return {
    id,
    topic: 'payments',
    category: 'payments',
    status: 'open',
    created_at: '2026-10-25T12:00:00Z',
    status_changed_at: '2026-10-25T12:00:00Z',
    opener: null,
    claimed_by: null,
    history_thread_id: null,
    ...over,
  }
}

describe('support store -- H40', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('keeps the key of an appeal for a retry of the same topic and text only', async () => {
    const store = useSupportStore()
    create.mockRejectedValue(new Error('timeout'))
    await store.createTicket('payments', 'help')
    await store.createTicket('payments', 'help') // a retry: the same key
    await store.createTicket('kyc', 'help') // another topic: another appeal
    const keys = create.mock.calls.map((call) => call[2])
    expect(keys[0]).toBeTruthy()
    expect(keys[1]).toBe(keys[0])
    expect(keys[2]).not.toBe(keys[0])
  })

  it('a superseded list load never writes over the newer one', async () => {
    const store = useSupportStore()
    let releaseOld: (v: unknown) => void = () => {}
    list
      .mockReturnValueOnce(new Promise((resolve) => (releaseOld = resolve)) as never)
      .mockResolvedValueOnce({ items: [row('new')], next_cursor: null })
    const old = store.fetchTickets({ status: 'spam' })
    await store.fetchTickets({})
    releaseOld({ items: [row('old')], next_cursor: null })
    await old
    expect(store.tickets.map((t) => t.id)).toEqual(['new'])
  })

  it("an action's answer replaces the card and the same row of the list", async () => {
    const store = useSupportStore()
    list.mockResolvedValue({ items: [row('t1'), row('t2')], next_cursor: null })
    card.mockResolvedValue(row('t1'))
    await store.fetchTickets({})
    await store.fetchTicket('t1')
    const taken = row('t1', {
      claimed_by: { user_id: 's1', first_name: 'Sam', last_name: null, email: null },
    })
    claim.mockResolvedValue(taken)
    expect(await store.claimTicket('t1')).toBe(true)
    expect(store.ticket?.claimed_by?.user_id).toBe('s1')
    expect(store.tickets[0].claimed_by?.user_id).toBe('s1')
    expect(store.tickets[1].claimed_by).toBeNull()
  })

  it('one action at a time: a second press while the first is in flight does nothing', async () => {
    const store = useSupportStore()
    let release: (v: SupportTicketRow) => void = () => {}
    claim.mockReturnValueOnce(new Promise((resolve) => (release = resolve)))
    const first = store.claimTicket('t1')
    expect(await store.claimTicket('t1')).toBe(false)
    release(row('t1'))
    await first
    expect(claim).toHaveBeenCalledTimes(1)
  })

  it('a refused action is kept with its name, for the card to say what happened', async () => {
    const store = useSupportStore()
    claim.mockRejectedValue(new Error('conflict'))
    expect(await store.claimTicket('t1')).toBe(false)
    expect(store.actionError?.action).toBe('claim')
  })

  it('the badge is unknown until read, and a failed read keeps the last value', async () => {
    const store = useSupportStore()
    expect(store.unread).toBeNull()
    unread.mockResolvedValueOnce({ unread: 3 })
    await store.fetchUnread()
    expect(store.unread).toBe(3)
    unread.mockRejectedValueOnce(new Error('502'))
    await store.fetchUnread()
    expect(store.unread).toBe(3)
    markRead.mockResolvedValueOnce({ unread: 0 })
    await store.markRead()
    expect(store.unread).toBe(0)
  })
})
