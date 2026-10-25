// =============================================================================
// AIVIS.ONE Frontend -- Support API (Ф-1)
// =============================================================================
//
// Typed wrappers for /api/v1/support/* and /api/v1/staff/support/*.
// Source of truth: backend/app/modules/support/router.py and
// staff_router.py -- paths, bodies, status codes. Request bodies come
// from api/generated.ts (EmptyBodyIn, SendMessageIn, SetStatusIn) and
// are not redeclared here.
//
// RESPONSE TYPES HAVE NO GENERATED COUNTERPART, ON PURPOSE.
// Every handler here returns `dict[str, Any]`: the backend is a PROXY
// that forwards comms' own payload -- as-is, or with every message of a
// feed rendered for its reader (H39, backend modules/support/
// translation.py) -- so there is nothing for OpenAPI to describe. The
// shapes below are read from three places, not guessed:
//   - backend/app/modules/support/service.py -- which keys survive
//     the proxy (e.g. `created` is stripped from the open-thread
//     response; list_support_threads assembles its own {threads: []}
//     shape from the local pointer table, not from comms directly);
//   - comms/app/api/messaging.py `_thread_out` / `_message_out` --
//     the actual serializers a comms response is built from, for the
//     calls service.py forwards untouched;
//   - backend/app/modules/support/translation.py render_for_client /
//     staff_feed -- the two feeds, which are rendered, not forwarded.
// If comms' serializer changes shape, these types drift silently --
// there is no schema to catch it, same as every other comms call this
// product makes.
//
// SupportThreadResponse IS SHARED across open / claim / status-change
// and every row of the staff queue, because all four come from the
// SAME `_thread_out` serializer in comms and none of them re-shapes
// it (see service.py: open_support_thread returns _thread_out minus
// "created"; claim_support_thread returns the "thread" sub-object
// unchanged; set_support_thread_status and list_operator_threads
// return it as-is, the latter with an ADDITIVE optional `unread`).
//
// `status` is typed as a closed literal union: the set is locked in
// comms (arch doc, ThreadStatus) and cheap to state precisely.
// `operator_kind` / `kind` are left as `string` -- this frontend does
// not own that contract and never branches on either value; typing
// them tighter would just be decoration.
//
// `unread?: number` (never `unread: number | null`) on list rows is
// deliberate: comms OMITS the key for a thread the caller does not
// take part in (an unclaimed pool row, or the user list when comms
// was unreachable for the unread lookup) -- omission means "not
// applicable", and a `null` or a synthesised `0` would say something
// comms never said. See service.py list_support_threads and
// list_operator_threads docstrings.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type { EmptyBodyIn, SendMessageIn, SetStatusIn } from '@/api/generated'

export interface SupportThreadResponse {
  id: string
  client: string
  operator_kind: string
  operator_value: string
  assignee: string | null
  kind: string
  status: 'open' | 'resolved' | 'closed'
  subject_type: string | null
  subject_id: string | null
  title: string | null
  priority: number | null
  last_message_at: string | null
  created_at: string | null
}

/** One message as comms stores it: the answer to a send or a reply. */
export interface SupportMessageResponse {
  id: string
  thread_id: string
  sender: string
  body: string
  created_at: string | null
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

// Every support list has comms' one listing shape (comms
// deploy/INTEGRATION.md section 5): `items` and `next_cursor`. The
// caller's own thread list is local and never has a second page, but it
// answers in the same shape so no reader has two to know.
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
 * One row of the caller's own thread list. Assembled by service.py
 * from the local pointer table, NOT from comms' _thread_out -- hence
 * the narrower shape (id + opened_at, plus the same optional unread).
 */
export interface SupportThreadListItem {
  id: string
  opened_at: string | null
  unread?: number
}

export interface SupportThreadListResponse {
  items: SupportThreadListItem[]
  next_cursor: string | null
}

/**
 * Who the client of a thread is, in this product's terms.
 *
 * NOT FROM comms (T-75). comms knows recipients by uuid and nothing
 * else; the backend adds this key to operator queue rows from its own
 * pointer table, which is why it is absent -- not null -- on a row
 * whose thread the backend does not recognise.
 *
 * The pieces arrive separately and the view joins them, matching how
 * the rest of the staff area renders a person (StaffUsersView.fullName).
 * Every field is optional on purpose: a profile may be half filled in,
 * and a Telegram-only account has no email at all.
 */
export interface SupportClientProfile {
  first_name?: string | null
  last_name?: string | null
  email?: string | null
}

export interface SupportOperatorThreadRow extends SupportThreadResponse {
  unread?: number
  client_profile?: SupportClientProfile
}

export interface SupportOperatorQueueResponse {
  items: SupportOperatorThreadRow[]
  next_cursor: string | null
}

export interface ListMessagesParams {
  limit?: number
  cursor?: string
}

export interface ListQueueParams {
  limit?: number
  cursor?: string
}

// ---------------------------------------------------------------------------
// User side -- /api/v1/support/*
// ---------------------------------------------------------------------------

/**
 * POST /api/v1/support/threads -- open the caller's support
 * conversation, or return the existing one. Idempotent; safe to call
 * before every send.
 *
 * Backend returns:
 *   200  the thread ("created" stripped -- see module header)
 *   502  comms unreachable, OR the recipient upsert has not caught
 *        up yet (code `comms_recipient_pending` in the body) -- both
 *        surface as the same ApiResponseError(502, ...) here; the
 *        message text (not re-declared as a type) is what tells them
 *        apart for a caller that reads it.
 */
export function openSupportThread(): Promise<SupportThreadResponse> {
  return api.post<SupportThreadResponse>('/api/v1/support/threads')
}

/**
 * GET /api/v1/support/threads -- the caller's own conversations.
 *
 * Answers even when comms is down: rows come back without `unread`
 * in that case, not as an error. Not paginated (see router.py).
 */
export function listSupportThreads(): Promise<SupportThreadListResponse> {
  return api.get<SupportThreadListResponse>('/api/v1/support/threads')
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

/**
 * POST /api/v1/support/threads/messages -- send one message into the
 * caller's own conversation. No thread id on the wire.
 *
 * 404 if the caller has never opened the channel (open first).
 */
export function sendSupportMessage(
  body: SendMessageIn['body'],
  idempotencyKey: string,
): Promise<SupportMessageResponse> {
  const payload: SendMessageIn = { body }
  return api.post<SupportMessageResponse>(
    '/api/v1/support/threads/messages',
    payload,
    idempotencyHeaders(idempotencyKey),
  )
}

/**
 * GET /api/v1/support/threads/{id}/messages -- that thread's feed,
 * newest first, keyset-paginated, every message rendered for the caller
 * (SupportClientMessage).
 *
 * 404 if `thread_id` is not this caller's (including a real thread
 * belonging to somebody else -- existence never leaks).
 */
export function getSupportThreadMessages(
  threadId: string,
  params?: ListMessagesParams,
): Promise<SupportClientMessageListResponse> {
  const qs = buildQueryString({
    limit: params?.limit,
    cursor: params?.cursor,
  })
  return api.get<SupportClientMessageListResponse>(
    `/api/v1/support/threads/${threadId}/messages${qs}`,
  )
}

/**
 * POST /api/v1/support/threads/{id}/read -- mark the caller's thread
 * read; returns the fresh unread count.
 */
export function markSupportThreadRead(threadId: string): Promise<SupportUnreadResponse> {
  const body: EmptyBodyIn = {}
  return api.post<SupportUnreadResponse>(`/api/v1/support/threads/${threadId}/read`, body)
}

// ---------------------------------------------------------------------------
// Staff side -- /api/v1/staff/support/*
// ---------------------------------------------------------------------------

/**
 * GET /api/v1/staff/support/threads -- the operator's queue: the
 * unclaimed pool plus their own claimed threads, most recently active
 * first (a supervisor gets every thread there is). Pool rows never
 * carry `unread` (see SupportOperatorThreadRow).
 */
export function listStaffSupportQueue(
  params?: ListQueueParams,
): Promise<SupportOperatorQueueResponse> {
  const qs = buildQueryString({
    limit: params?.limit,
    cursor: params?.cursor,
  })
  return api.get<SupportOperatorQueueResponse>(`/api/v1/staff/support/threads${qs}`)
}

/**
 * POST /api/v1/staff/support/threads/{id}/claim -- take an unclaimed
 * request.
 *
 * Backend hands back only the thread object. A repeat claim by the SAME
 * operator succeeds (200) with the same thread -- comms answers "is it
 * yours now", so a lost response is safe to retry. Claiming one a
 * colleague already took is 409 (`support_thread_already_claimed`).
 */
export function claimStaffSupportThread(threadId: string): Promise<SupportThreadResponse> {
  const body: EmptyBodyIn = {}
  return api.post<SupportThreadResponse>(`/api/v1/staff/support/threads/${threadId}/claim`, body)
}

/**
 * GET /api/v1/staff/support/threads/{id}/messages -- read one known
 * request, newest first, keyset-paginated.
 *
 * NOT THE USER FEED'S TYPE since H39: both feeds are rendered for their
 * reader (translation.py) -- the person's carries no original of a
 * reply, the operator's carries the original and the translation state
 * of every message -- so one serializer upstream now gives two shapes
 * here.
 *
 * 404 if the id names no support thread this product created. NOT
 * restricted to threads this operator claimed -- the queue shows the
 * unclaimed pool, and an operator reads a request before deciding to
 * take it. Claiming gates writing, not reading.
 */
export function getStaffSupportThreadMessages(
  threadId: string,
  params?: ListMessagesParams,
): Promise<SupportStaffMessageListResponse> {
  const qs = buildQueryString({
    limit: params?.limit,
    cursor: params?.cursor,
  })
  return api.get<SupportStaffMessageListResponse>(
    `/api/v1/staff/support/threads/${threadId}/messages${qs}`,
  )
}

/**
 * POST /api/v1/staff/support/threads/{id}/messages -- answer as this
 * operator.
 *
 * 409 (`support_thread_not_claimed`) if the operator has not claimed
 * the conversation yet -- comms' 403 forwarded as an actionable
 * conflict rather than a bare auth failure.
 */
export function replyToStaffSupportThread(
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
 * POST /api/v1/staff/support/threads/{id}/status -- resolve or close.
 *
 * `open` is not a valid target (see SetStatusIn on the backend): comms
 * has a manual return to `open`, and offering it is the ticket work of
 * H40. Until then a closed thread revives when the CLIENT writes into it.
 */
export function setStaffSupportThreadStatus(
  threadId: string,
  status: SetStatusIn['status'],
): Promise<SupportThreadResponse> {
  const payload: SetStatusIn = { status }
  return api.post<SupportThreadResponse>(
    `/api/v1/staff/support/threads/${threadId}/status`,
    payload,
  )
}

/**
 * POST /api/v1/staff/support/threads/{id}/messages/{mid}/translation/retry
 * -- ask again for a message whose translation failed (H39). Offered only
 * where the feed says `retryable`; 409 when there is nothing to retry
 * (in progress, done, or declined -- final), 404 when the message is out
 * of the thread's reach.
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
