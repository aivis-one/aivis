// =============================================================================
// AIVIS.ONE Frontend -- Support Store (Ф-1, H40 tickets)
// =============================================================================
//
// Pinia store for support. Two separate sections: the PERSON's one
// conversation (InvestorSupportView, shared by the buyer, the integrator and
// the project), and the OPERATOR's tickets -- the list (StaffSupportView)
// and one ticket's card (StaffSupportTicketView).
//
// WHY ONE STORE, NOT TWO (per stores/portfolio.ts's own header, same
// question for a different pair of surfaces): a staff member is also a
// person with their own conversation, and both halves share the send
// discipline below. The two sections share no state.
//
// ERROR SHAPE: `{ message, status } | null`, never a bare boolean. A
// 502/504 (comms unreachable) is a NORMAL backend answer, not a frontend
// fault -- see app/core/comms.py comms_request docstring. Carrying `status`
// lets a screen tell "support is temporarily down" (502/504) apart from
// "you can't do that" (404/409).
//
// ONE PRESS OF SEND, ONE KEY. The Idempotency-Key is minted when the person
// presses send and kept with the text until comms confirms it, so a retry
// after a failure or a timeout sends under the SAME key and comms answers
// with what it already stored. A different text is a different message
// and gets a new key. The form's appeal follows the same rule, keyed by
// topic and text together.
//
// NO OPTIMISTIC MUTATION ON SEND. A successful send stores nothing in the
// feed; the screen re-reads the first page.
//
// EPOCH GUARDS (same FP-17 pattern as portfolio.ts / transactions.ts): one
// counter per surface that loads -- the person's feed, the staff list, the
// staff card, the staff feed. A superseded load never writes over a newer
// one. Per-ticket actions are guarded by an in-flight flag instead: a
// second click while the first is in flight is a no-op.
// =============================================================================

import { ref } from 'vue'
import { defineStore } from 'pinia'

import {
  assignStaffTicket,
  claimStaffTicket,
  createSupportTicket,
  getStaffThreadMessages,
  getStaffTicket,
  getSupportMessages,
  getSupportUnread,
  listStaffOperators,
  listStaffTickets,
  markSupportRead,
  releaseStaffTicket,
  reopenStaffTicket,
  replyToStaffThread,
  retryStaffSupportTranslation,
  sendSupportMessage,
  setStaffTicketStatus,
} from '@/api/support'
import { ApiResponseError } from '@/api/client'
import type {
  ListTicketsParams,
  SupportClientMessage,
  SupportClosingStatus,
  SupportPerson,
  SupportStaffMessage,
  SupportTicketRow,
  SupportTopic,
} from '@/api/support'

export interface SupportActionError {
  message: string
  status?: number
}

function toActionError(err: unknown): SupportActionError {
  if (err instanceof ApiResponseError) {
    return { message: err.detail, status: err.status }
  }
  return { message: err instanceof Error ? err.message : String(err) }
}

/** One send on its way to comms, with the key it is sent under. */
interface Pending {
  what: string
  key: string
}

/**
 * The key for sending `what`: the pending one when this is a retry of the
 * same thing, a fresh one otherwise. Minted here, on the press of send --
 * never per HTTP attempt.
 */
function keyFor(pending: Pending | null, what: string): Pending {
  if (pending !== null && pending.what === what) return pending
  return { what, key: crypto.randomUUID() }
}

/** What a staff ticket action is, for its in-flight flag and its error. */
export type TicketAction = 'claim' | 'assign' | 'release' | 'status' | 'reopen'

export const useSupportStore = defineStore('support', () => {
  // ---------------------------------------------------------------------
  // The person -- one conversation
  // ---------------------------------------------------------------------
  const messages = ref<SupportClientMessage[]>([])
  const messagesNextCursor = ref<string | null>(null)
  const messagesLoaded = ref<boolean>(false)
  const messagesLoading = ref<boolean>(false)
  const messagesError = ref<SupportActionError | null>(null)
  const olderLoading = ref<boolean>(false)
  const olderError = ref<SupportActionError | null>(null)

  const sending = ref<boolean>(false)
  const sendError = ref<SupportActionError | null>(null)
  let pendingSend: Pending | null = null

  const creatingTicket = ref<boolean>(false)
  const createTicketError = ref<SupportActionError | null>(null)
  let pendingTicket: Pending | null = null

  // The Support row's badge. null = not known yet (or the last read
  // failed) -- never a guessed 0.
  const unread = ref<number | null>(null)

  let feedEpoch = 0

  /**
   * First page (or a fresh reload) of the conversation.
   *
   * `silent` (H39): the re-read while a translation is on its way
   * (useTranslationPoll). It neither shows the loader nor touches the
   * error -- a missed re-read is simply the next tick's work.
   */
  async function fetchMessages(opts?: { silent?: boolean }): Promise<void> {
    const silent = opts?.silent === true
    const epoch = ++feedEpoch
    if (!silent) {
      messagesLoading.value = true
      messagesError.value = null
    }
    try {
      const resp = await getSupportMessages()
      if (epoch !== feedEpoch) return
      messages.value = resp.items
      messagesNextCursor.value = resp.next_cursor
      messagesLoaded.value = true
      olderError.value = null
    } catch (err) {
      if (epoch !== feedEpoch || silent) return
      messagesError.value = toActionError(err)
    } finally {
      if (epoch === feedEpoch && !silent) messagesLoading.value = false
    }
  }

  /** The next, older page of the conversation, appended (newest first). */
  async function fetchOlderMessages(): Promise<void> {
    const cursor = messagesNextCursor.value
    if (cursor === null || olderLoading.value) return
    const epoch = feedEpoch
    olderLoading.value = true
    olderError.value = null
    try {
      const resp = await getSupportMessages({ cursor })
      if (epoch !== feedEpoch) return
      const seen = new Set(messages.value.map((m) => m.id))
      messages.value = [...messages.value, ...resp.items.filter((m) => !seen.has(m.id))]
      messagesNextCursor.value = resp.next_cursor
    } catch (err) {
      if (epoch !== feedEpoch) return
      olderError.value = toActionError(err)
    } finally {
      olderLoading.value = false
    }
  }

  /**
   * A message written in the conversation. The backend decides where it
   * goes (the latest open ticket, else the latest, else a new "other").
   */
  async function sendMessage(body: string): Promise<boolean> {
    if (sending.value) return false
    pendingSend = keyFor(pendingSend, body)
    sending.value = true
    sendError.value = null
    try {
      await sendSupportMessage(body, pendingSend.key)
      pendingSend = null
      return true
    } catch (err) {
      sendError.value = toActionError(err)
      return false
    } finally {
      sending.value = false
    }
  }

  /** An appeal through the form: a new ticket, every time. */
  async function createTicket(topic: SupportTopic, body: string): Promise<boolean> {
    if (creatingTicket.value) return false
    pendingTicket = keyFor(pendingTicket, `${topic}\n${body}`)
    creatingTicket.value = true
    createTicketError.value = null
    try {
      await createSupportTicket(topic, body, pendingTicket.key)
      pendingTicket = null
      return true
    } catch (err) {
      createTicketError.value = toActionError(err)
      return false
    } finally {
      creatingTicket.value = false
    }
  }

  /**
   * Read up to now. Fire-and-forget for the screen: a failure leaves the
   * badge as it was -- read bookkeeping is nothing the person can retry.
   */
  async function markRead(): Promise<void> {
    try {
      const resp = await markSupportRead()
      unread.value = resp.unread
    } catch {
      // The badge keeps its last known value; the next read corrects it.
    }
  }

  /** The Support row's badge. A failure keeps the last known value. */
  async function fetchUnread(): Promise<void> {
    try {
      const resp = await getSupportUnread()
      unread.value = resp.unread
    } catch {
      // Same rule as the bell (notifications store): never reset to 0 on
      // an error.
    }
  }

  // ---------------------------------------------------------------------
  // The operator -- the ticket list
  // ---------------------------------------------------------------------
  const tickets = ref<SupportTicketRow[]>([])
  const ticketsNextCursor = ref<string | null>(null)
  const ticketsLoaded = ref<boolean>(false)
  const ticketsLoading = ref<boolean>(false)
  const ticketsError = ref<SupportActionError | null>(null)
  const moreTicketsLoading = ref<boolean>(false)
  const moreTicketsError = ref<SupportActionError | null>(null)
  let ticketsFilter: ListTicketsParams = {}
  let ticketsEpoch = 0

  /** The first page under `filter`; remembered for the next pages. */
  async function fetchTickets(filter: ListTicketsParams): Promise<void> {
    const epoch = ++ticketsEpoch
    ticketsFilter = { ...filter, cursor: undefined }
    ticketsLoading.value = true
    ticketsError.value = null
    moreTicketsError.value = null
    try {
      const resp = await listStaffTickets(ticketsFilter)
      if (epoch !== ticketsEpoch) return
      tickets.value = resp.items
      ticketsNextCursor.value = resp.next_cursor
      ticketsLoaded.value = true
    } catch (err) {
      if (epoch !== ticketsEpoch) return
      ticketsError.value = toActionError(err)
    } finally {
      if (epoch === ticketsEpoch) ticketsLoading.value = false
    }
  }

  /** The next page under the same filter, appended. */
  async function fetchMoreTickets(): Promise<void> {
    const cursor = ticketsNextCursor.value
    if (cursor === null || moreTicketsLoading.value) return
    const epoch = ticketsEpoch
    moreTicketsLoading.value = true
    moreTicketsError.value = null
    try {
      const resp = await listStaffTickets({ ...ticketsFilter, cursor })
      if (epoch !== ticketsEpoch) return
      const seen = new Set(tickets.value.map((row) => row.id))
      tickets.value = [...tickets.value, ...resp.items.filter((row) => !seen.has(row.id))]
      ticketsNextCursor.value = resp.next_cursor
    } catch (err) {
      if (epoch !== ticketsEpoch) return
      moreTicketsError.value = toActionError(err)
    } finally {
      moreTicketsLoading.value = false
    }
  }

  // ---------------------------------------------------------------------
  // The operator -- one ticket's card
  // ---------------------------------------------------------------------
  const ticket = ref<SupportTicketRow | null>(null)
  const ticketLoading = ref<boolean>(false)
  const ticketError = ref<SupportActionError | null>(null)
  let ticketEpoch = 0

  const acting = ref<TicketAction | null>(null)
  const actionError = ref<{ action: TicketAction; error: SupportActionError } | null>(null)

  const operators = ref<SupportPerson[]>([])
  const operatorsLoaded = ref<boolean>(false)
  const operatorsError = ref<SupportActionError | null>(null)

  /** The card of one ticket, by its thread id. */
  async function fetchTicket(threadId: string): Promise<void> {
    const epoch = ++ticketEpoch
    if (ticket.value?.id !== threadId) ticket.value = null
    ticketLoading.value = true
    ticketError.value = null
    actionError.value = null
    try {
      const resp = await getStaffTicket(threadId)
      if (epoch !== ticketEpoch) return
      ticket.value = resp
    } catch (err) {
      if (epoch !== ticketEpoch) return
      ticketError.value = toActionError(err)
    } finally {
      if (epoch === ticketEpoch) ticketLoading.value = false
    }
  }

  // The card's answer replaces the card, and the same row of the list if
  // the list holds it -- so going back shows the change without a reload.
  function adopt(updated: SupportTicketRow): void {
    if (ticket.value?.id === updated.id) ticket.value = updated
    const idx = tickets.value.findIndex((row) => row.id === updated.id)
    if (idx !== -1) tickets.value[idx] = updated
  }

  async function act(
    action: TicketAction,
    call: () => Promise<SupportTicketRow>,
  ): Promise<boolean> {
    if (acting.value !== null) return false
    acting.value = action
    actionError.value = null
    try {
      adopt(await call())
      return true
    } catch (err) {
      actionError.value = { action, error: toActionError(err) }
      return false
    } finally {
      acting.value = null
    }
  }

  const claimTicket = (id: string) => act('claim', () => claimStaffTicket(id))
  const assignTicket = (id: string, assignee: string) =>
    act('assign', () => assignStaffTicket(id, assignee))
  const releaseTicket = (id: string) => act('release', () => releaseStaffTicket(id))
  const setTicketStatus = (id: string, status: SupportClosingStatus) =>
    act('status', () => setStaffTicketStatus(id, status))
  const reopenTicket = (id: string) => act('reopen', () => reopenStaffTicket(id))

  /** Every active operator, for "hand over to". Loaded once. */
  async function fetchOperators(): Promise<void> {
    if (operatorsLoaded.value) return
    operatorsError.value = null
    try {
      const resp = await listStaffOperators()
      operators.value = resp.items
      operatorsLoaded.value = true
    } catch (err) {
      operatorsError.value = toActionError(err)
    }
  }

  // ---------------------------------------------------------------------
  // The operator -- one thread's feed (a ticket's, or a history's)
  // ---------------------------------------------------------------------
  const staffMessages = ref<SupportStaffMessage[]>([])
  const staffMessagesThreadId = ref<string | null>(null)
  const staffMessagesNextCursor = ref<string | null>(null)
  const staffMessagesLoading = ref<boolean>(false)
  const staffMessagesError = ref<SupportActionError | null>(null)
  let staffFeedEpoch = 0

  const replying = ref<boolean>(false)
  const replyError = ref<SupportActionError | null>(null)
  // One pending reply per thread: the same rule as the person's send.
  const pendingReplies: Record<string, Pending> = {}

  /** First page of one thread, for an operator. `silent` as on the person's side. */
  async function fetchStaffMessages(threadId: string, opts?: { silent?: boolean }): Promise<void> {
    const silent = opts?.silent === true
    const epoch = ++staffFeedEpoch
    if (staffMessagesThreadId.value !== threadId) {
      staffMessages.value = []
      staffMessagesNextCursor.value = null
    }
    staffMessagesThreadId.value = threadId
    if (!silent) {
      staffMessagesLoading.value = true
      staffMessagesError.value = null
    }
    try {
      const resp = await getStaffThreadMessages(threadId)
      if (epoch !== staffFeedEpoch) return
      staffMessages.value = resp.items
      staffMessagesNextCursor.value = resp.next_cursor
    } catch (err) {
      if (epoch !== staffFeedEpoch || silent) return
      staffMessagesError.value = toActionError(err)
    } finally {
      if (epoch === staffFeedEpoch && !silent) staffMessagesLoading.value = false
    }
  }

  /**
   * Answer the person in a ticket this operator took. A 409 is the
   * backend saying "take it first" (or "a history is read-only").
   */
  async function replyToThread(threadId: string, body: string): Promise<boolean> {
    if (replying.value) return false
    const pending = keyFor(pendingReplies[threadId] ?? null, body)
    pendingReplies[threadId] = pending
    replying.value = true
    replyError.value = null
    try {
      await replyToStaffThread(threadId, body, pending.key)
      delete pendingReplies[threadId]
      return true
    } catch (err) {
      replyError.value = toActionError(err)
      return false
    } finally {
      replying.value = false
    }
  }

  // Per MESSAGE: a feed holds many messages, and one retry in flight must
  // not light up every other message's button.
  const retryingTranslation = ref<Record<string, boolean>>({})
  const retryTranslationErrors = ref<Record<string, SupportActionError | null>>({})

  /**
   * Ask again for a message whose translation failed (H39); on success
   * the feed is re-read silently, so the message shows "translating".
   */
  async function retryTranslation(threadId: string, messageId: string): Promise<void> {
    if (retryingTranslation.value[messageId]) return
    retryingTranslation.value[messageId] = true
    retryTranslationErrors.value[messageId] = null
    try {
      await retryStaffSupportTranslation(threadId, messageId)
      await fetchStaffMessages(threadId, { silent: true })
    } catch (err) {
      retryTranslationErrors.value[messageId] = toActionError(err)
    } finally {
      retryingTranslation.value[messageId] = false
    }
  }

  // ---------------------------------------------------------------------
  // Session boundary
  // ---------------------------------------------------------------------

  /**
   * Full reset, wired into stores/sessionReset.ts. Bumps every epoch
   * first so an in-flight load cannot repopulate cleared state after it
   * resolves (same FP-17 pattern as portfolio.ts).
   */
  function reset(): void {
    ++feedEpoch
    ++ticketsEpoch
    ++ticketEpoch
    ++staffFeedEpoch

    messages.value = []
    messagesNextCursor.value = null
    messagesLoaded.value = false
    messagesLoading.value = false
    messagesError.value = null
    olderLoading.value = false
    olderError.value = null
    sending.value = false
    sendError.value = null
    pendingSend = null
    creatingTicket.value = false
    createTicketError.value = null
    pendingTicket = null
    unread.value = null

    tickets.value = []
    ticketsNextCursor.value = null
    ticketsLoaded.value = false
    ticketsLoading.value = false
    ticketsError.value = null
    moreTicketsLoading.value = false
    moreTicketsError.value = null
    ticketsFilter = {}

    ticket.value = null
    ticketLoading.value = false
    ticketError.value = null
    acting.value = null
    actionError.value = null
    operators.value = []
    operatorsLoaded.value = false
    operatorsError.value = null

    staffMessages.value = []
    staffMessagesThreadId.value = null
    staffMessagesNextCursor.value = null
    staffMessagesLoading.value = false
    staffMessagesError.value = null
    replying.value = false
    replyError.value = null
    for (const threadId of Object.keys(pendingReplies)) delete pendingReplies[threadId]
    retryingTranslation.value = {}
    retryTranslationErrors.value = {}
  }

  return {
    // the person's conversation
    messages,
    messagesNextCursor,
    messagesLoaded,
    messagesLoading,
    messagesError,
    olderLoading,
    olderError,
    fetchMessages,
    fetchOlderMessages,
    sending,
    sendError,
    sendMessage,
    creatingTicket,
    createTicketError,
    createTicket,
    unread,
    markRead,
    fetchUnread,

    // the operator's list
    tickets,
    ticketsNextCursor,
    ticketsLoaded,
    ticketsLoading,
    ticketsError,
    moreTicketsLoading,
    moreTicketsError,
    fetchTickets,
    fetchMoreTickets,

    // the operator's card
    ticket,
    ticketLoading,
    ticketError,
    fetchTicket,
    acting,
    actionError,
    claimTicket,
    assignTicket,
    releaseTicket,
    setTicketStatus,
    reopenTicket,
    operators,
    operatorsLoaded,
    operatorsError,
    fetchOperators,

    // the operator's feed
    staffMessages,
    staffMessagesThreadId,
    staffMessagesNextCursor,
    staffMessagesLoading,
    staffMessagesError,
    fetchStaffMessages,
    replying,
    replyError,
    replyToThread,
    retryingTranslation,
    retryTranslationErrors,
    retryTranslation,

    // session boundary
    reset,
  }
})
