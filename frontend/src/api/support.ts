// =============================================================================
// AIVIS.ONE Frontend -- Support API (Ф-1, H40 tickets)
// =============================================================================
//
// Typed wrappers for /api/v1/support/* and /api/v1/staff/support/*.
// Source of truth: backend/app/modules/support/router.py and
// staff_router.py -- paths, bodies, status codes. Request bodies come
// from api/generated.ts (TicketIn, SendMessageIn, SetTicketStatusIn,
// AssignIn, EmptyBodyIn) and are not redeclared here.
//
// RESPONSE TYPES HAVE NO GENERATED COUNTERPART, ON PURPOSE. Every handler
// returns `dict[str, Any]`: a message is comms' own (forwarded, or rendered
// for its reader -- backend modules/support/translation.py), and a ticket
// is assembled by the backend from its own table (service.py ticket_out,
// _ticket_rows). The shapes below are read from those functions, not
// guessed; if they change, these types drift silently -- there is no
// schema to catch it, same as every other comms call this product makes.
//
// THE PERSON HAS ONE CONVERSATION (H40). However many tickets it holds, the
// person's side names no thread: the form opens a ticket, a message goes to
// the conversation (the backend picks the ticket), and the feed glues every
// thread of theirs into one, newest first. Only the staff side names
// threads -- by the comms thread id, the ticket's id everywhere here.
//
// Every list has comms' one listing shape (comms deploy/INTEGRATION.md
// section 5): `items` and `next_cursor`.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  AssignIn,
  EmptyBodyIn,
  SendMessageIn,
  SetTicketStatusIn,
  TicketIn,
} from '@/api/generated'

/** A topic of the form (backend models.TOPICS keys). */
export type SupportTopic = TicketIn['topic']

/** What a topic counts as (backend models.CATEGORIES). */
export type SupportCategory =
  | 'payments'
  | 'withdrawals'
  | 'verification'
  | 'purchases'
  | 'tech'
  | 'other'

/** A ticket's status (backend models.STATUSES). */
export type SupportTicketStatus = 'open' | 'resolved' | 'rejected' | 'duplicate' | 'spam'

/** How an open ticket is closed (backend models.CLOSING_STATUSES). */
export type SupportClosingStatus = SetTicketStatusIn['status']

/** The topics in the order the form offers them. */
export const SUPPORT_TOPICS: readonly SupportTopic[] = [
  'payments',
  'withdrawal',
  'kyc',
  'purchases',
  'technical',
  'other',
]

/** The categories in the order the staff filter offers them. */
export const SUPPORT_CATEGORIES: readonly SupportCategory[] = [
  'payments',
  'withdrawals',
  'verification',
  'purchases',
  'tech',
  'other',
]

/** The closing statuses in the order the card offers them. */
export const SUPPORT_CLOSING_STATUSES: readonly SupportClosingStatus[] = [
  'resolved',
  'rejected',
  'duplicate',
  'spam',
]

/** A ticket as the backend describes it -- codes, never labels. */
export interface SupportTicket {
  /** The comms thread id: the ticket's id everywhere. */
  id: string
  topic: SupportTopic
  category: SupportCategory
  status: SupportTicketStatus
  created_at: string | null
  status_changed_at: string
}

/** One message as comms stores it: the answer to a send or a reply. */
export interface SupportMessageResponse {
  id: string
  thread_id: string
  sender: string
  body: string
  created_at: string | null
}

/** The answer to the form: the new ticket and its first message. */
export interface SupportTicketCreated {
  ticket: SupportTicket
  message: SupportMessageResponse
}

/**
 * One message of the person's own feed (H39, render_for_client).
 *
 * `body` is what the person may read: their own text, a staff reply in
 * their language, or NULL -- and then `translation` says why: a
 * translation is on its way, or there will be none. A reply in a language
 * the person does not read never arrives here (fail-closed on the
 * backend), so a null body is never to be filled from anywhere else.
 */
export type SupportClientTranslation = 'translating' | 'unavailable'

export interface SupportClientMessage {
  id: string
  thread_id?: string
  sender: string
  body: string | null
  created_at: string | null
  translation: SupportClientTranslation | null
}

export interface SupportClientMessageListResponse {
  items: SupportClientMessage[]
  next_cursor: string | null
}

/**
 * comms' variant state of a message in one language (its INTEGRATION.md
 * section 12), as the staff feed reports it. A string the backend may
 * extend: an unknown one is read as "no translation, not retryable".
 */
export type SupportVariantState =
  | 'ready'
  | 'impossible'
  | 'not_needed'
  | 'preparing'
  | 'not_requested'

/**
 * The translation block of a staff feed item (H39, staff_feed).
 *
 * On a person's message: the translation into the support language --
 * the item's `body` IS it when `state` is ready. On a staff reply to a
 * person of another language: what the person will read, in
 * `variant_body` once ready. `retryable` -- the job ended without an
 * answer, and asking again is offered.
 */
export interface SupportStaffTranslation {
  locale: string
  state: SupportVariantState | string
  source_locale: string | null
  retryable: boolean
  variant_body?: string | null
}

/**
 * One message of the staff feed: comms' message, `body` in the support
 * language when a translation is ready, `original` the author's own text
 * (staff only), and the translation block -- null on a staff reply to a
 * person who reads the support language.
 */
export interface SupportStaffMessage {
  id: string
  thread_id: string
  sender: string
  body: string | null
  created_at: string | null
  original: string | null
  translation: SupportStaffTranslation | null
}

export interface SupportStaffMessageListResponse {
  items: SupportStaffMessage[]
  next_cursor: string | null
}

/** The answer to a staff retry of a translation. */
export interface SupportTranslationRetryResponse {
  message_id: string
  locale: string
  attempt: number
  state: 'preparing'
}

export interface SupportUnreadResponse {
  unread: number
}

/**
 * A person, for an operator (service.py _person): the pieces, joined by
 * the view (StaffUsersView's way). `email` is null for a Telegram-only
 * account; a profile may be half filled in.
 */
export interface SupportPerson {
  user_id: string
  first_name: string | null
  last_name: string | null
  email: string | null
}

/**
 * A ticket as an operator reads it -- one row of the list, and the card
 * (a signal opens the card without the list). `history_thread_id` is the
 * person's conversation from before tickets, read-only, or null.
 */
export interface SupportTicketRow extends SupportTicket {
  opener: SupportPerson | null
  claimed_by: SupportPerson | null
  history_thread_id: string | null
}

export interface SupportTicketListResponse {
  items: SupportTicketRow[]
  next_cursor: string | null
}

export interface SupportOperatorListResponse {
  items: SupportPerson[]
  next_cursor: null
}

export interface ListMessagesParams {
  limit?: number
  cursor?: string
}

/**
 * The staff list's filters. `status` absent lists every ticket but spam;
 * `spam` is the spam tab. The day's edges carry the operator's own zone
 * (an edge without one is a 400): ISO strings with an offset.
 */
export interface ListTicketsParams {
  category?: readonly SupportCategory[]
  status?: SupportTicketStatus
  created_from?: string
  created_to?: string
  limit?: number
  cursor?: string
}

/**
 * The Idempotency-Key header for one message. The key is born when the
 * person presses send and is reused on every retry of THAT message --
 * the store keeps it with the draft (stores/support.ts). A new key on a
 * retry would make comms store a second message and ping a second time.
 */
function idempotencyHeaders(idempotencyKey: string): Record<string, string> {
  return { 'Idempotency-Key': idempotencyKey }
}

// ---------------------------------------------------------------------------
// The person's side -- /api/v1/support/*
// ---------------------------------------------------------------------------

/**
 * POST /api/v1/support/tickets -- an appeal through the form: a topic and
 * the text. Every submit is a new ticket; a retry under the same key is
 * the same ticket.
 *
 * 502 when comms is unreachable or has not caught up with this person yet
 * (code `comms_recipient_pending`); 422 for an unknown topic.
 */
export function createSupportTicket(
  topic: SupportTopic,
  body: TicketIn['body'],
  idempotencyKey: string,
): Promise<SupportTicketCreated> {
  const payload: TicketIn = { topic, body }
  return api.post<SupportTicketCreated>(
    '/api/v1/support/tickets',
    payload,
    idempotencyHeaders(idempotencyKey),
  )
}

/**
 * POST /api/v1/support/messages -- a message written in the conversation:
 * into the latest open ticket, else the latest ticket (back to work),
 * else a new ticket "other". No thread id on the wire.
 */
export function sendSupportMessage(
  body: SendMessageIn['body'],
  idempotencyKey: string,
): Promise<SupportMessageResponse> {
  const payload: SendMessageIn = { body }
  return api.post<SupportMessageResponse>(
    '/api/v1/support/messages',
    payload,
    idempotencyHeaders(idempotencyKey),
  )
}

/**
 * GET /api/v1/support/messages -- the caller's conversation, every thread
 * of theirs glued into one feed, newest first, each message rendered for
 * them (SupportClientMessage). A malformed cursor is a 400.
 */
export function getSupportMessages(
  params?: ListMessagesParams,
): Promise<SupportClientMessageListResponse> {
  const qs = buildQueryString({ limit: params?.limit, cursor: params?.cursor })
  return api.get<SupportClientMessageListResponse>(`/api/v1/support/messages${qs}`)
}

/** POST /api/v1/support/read -- read up to now, in the whole conversation. */
export function markSupportRead(): Promise<SupportUnreadResponse> {
  const body: EmptyBodyIn = {}
  return api.post<SupportUnreadResponse>('/api/v1/support/read', body)
}

/**
 * GET /api/v1/support/unread -- what the caller has not read, summed over
 * the whole conversation: the Support row's badge. 0 with no conversation.
 */
export function getSupportUnread(): Promise<SupportUnreadResponse> {
  return api.get<SupportUnreadResponse>('/api/v1/support/unread')
}

// ---------------------------------------------------------------------------
// Staff side -- /api/v1/staff/support/*
// ---------------------------------------------------------------------------

/**
 * GET /api/v1/staff/support/tickets -- every ticket, newest appeal first,
 * with the filters of ListTicketsParams. Every operator sees every ticket.
 */
export function listStaffTickets(params?: ListTicketsParams): Promise<SupportTicketListResponse> {
  const qs = buildQueryString({
    category: params?.category,
    status: params?.status,
    created_from: params?.created_from,
    created_to: params?.created_to,
    limit: params?.limit,
    cursor: params?.cursor,
  })
  return api.get<SupportTicketListResponse>(`/api/v1/staff/support/tickets${qs}`)
}

/** GET /api/v1/staff/support/tickets/{id} -- one ticket's card. 404 for a history. */
export function getStaffTicket(threadId: string): Promise<SupportTicketRow> {
  return api.get<SupportTicketRow>(`/api/v1/staff/support/tickets/${threadId}`)
}

/** GET /api/v1/staff/support/operators -- who a ticket can be handed to. */
export function listStaffOperators(): Promise<SupportOperatorListResponse> {
  return api.get<SupportOperatorListResponse>('/api/v1/staff/support/operators')
}

/**
 * POST .../tickets/{id}/claim -- take a ticket: the act that grants the
 * right to reply. A repeat by the same operator succeeds; a colleague's
 * ticket is 409 (`support_thread_already_claimed`). Answers the card.
 */
export function claimStaffTicket(threadId: string): Promise<SupportTicketRow> {
  const body: EmptyBodyIn = {}
  return api.post<SupportTicketRow>(`/api/v1/staff/support/tickets/${threadId}/claim`, body)
}

/**
 * POST .../tickets/{id}/assign -- hand a ticket to another operator; 422
 * unless an active one, 409 when the ticket changed hands meanwhile.
 */
export function assignStaffTicket(threadId: string, assignee: string): Promise<SupportTicketRow> {
  const payload: AssignIn = { assignee }
  return api.post<SupportTicketRow>(`/api/v1/staff/support/tickets/${threadId}/assign`, payload)
}

/** POST .../tickets/{id}/release -- return a ticket to the pool. */
export function releaseStaffTicket(threadId: string): Promise<SupportTicketRow> {
  const body: EmptyBodyIn = {}
  return api.post<SupportTicketRow>(`/api/v1/staff/support/tickets/${threadId}/release`, body)
}

/**
 * POST .../tickets/{id}/status -- close an OPEN ticket one of four ways;
 * 409 for one that is not open, or changed meanwhile.
 */
export function setStaffTicketStatus(
  threadId: string,
  status: SupportClosingStatus,
): Promise<SupportTicketRow> {
  const payload: SetTicketStatusIn = { status }
  return api.post<SupportTicketRow>(`/api/v1/staff/support/tickets/${threadId}/status`, payload)
}

/**
 * POST .../tickets/{id}/reopen -- back to work; spam only within its
 * retention (409 after), 404 once the bin took it.
 */
export function reopenStaffTicket(threadId: string): Promise<SupportTicketRow> {
  const body: EmptyBodyIn = {}
  return api.post<SupportTicketRow>(`/api/v1/staff/support/tickets/${threadId}/reopen`, body)
}

/**
 * GET .../threads/{id}/messages -- read a ticket or a person's history,
 * newest first. Not restricted to tickets this operator took: taking
 * gates writing, not reading.
 */
export function getStaffThreadMessages(
  threadId: string,
  params?: ListMessagesParams,
): Promise<SupportStaffMessageListResponse> {
  const qs = buildQueryString({ limit: params?.limit, cursor: params?.cursor })
  return api.get<SupportStaffMessageListResponse>(
    `/api/v1/staff/support/threads/${threadId}/messages${qs}`,
  )
}

/**
 * POST .../threads/{id}/messages -- answer the person in a ticket you
 * took. 409 (`support_thread_not_claimed`) if you have not; 409
 * (`support_history_read_only`) for a history.
 */
export function replyToStaffThread(
  threadId: string,
  body: SendMessageIn['body'],
  idempotencyKey: string,
): Promise<SupportMessageResponse> {
  const payload: SendMessageIn = { body }
  return api.post<SupportMessageResponse>(
    `/api/v1/staff/support/threads/${threadId}/messages`,
    payload,
    idempotencyHeaders(idempotencyKey),
  )
}

/**
 * POST .../threads/{id}/messages/{mid}/translation/retry -- ask again for
 * a message whose translation failed (H39). Offered only where the feed
 * says `retryable`; 409 when there is nothing to retry, 404 when the
 * message is out of the thread's reach.
 */
export function retryStaffSupportTranslation(
  threadId: string,
  messageId: string,
): Promise<SupportTranslationRetryResponse> {
  const body: EmptyBodyIn = {}
  return api.post<SupportTranslationRetryResponse>(
    `/api/v1/staff/support/threads/${threadId}/messages/${messageId}/translation/retry`,
    body,
  )
}
