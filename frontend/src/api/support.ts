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
// that forwards comms' own payload as-is, so there is nothing for
// OpenAPI to describe. The shapes below are read from two places, not
// guessed:
//   - backend/app/modules/support/service.py -- which keys survive
//     the proxy (e.g. `created` is stripped from the open-thread
//     response; list_support_threads assembles its own {threads: []}
//     shape from the local pointer table, not from comms directly);
//   - comms/app/api/messaging.py `_thread_out` / `_message_out` --
//     the actual serializers a comms response is built from, for the
//     calls service.py forwards untouched.
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

export interface SupportMessageResponse {
  id: string
  thread_id: string
  sender: string
  body: string
  created_at: string | null
}

export interface SupportMessageListResponse {
  messages: SupportMessageResponse[]
  next_cursor: string | null
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
  threads: SupportThreadListItem[]
}

export interface SupportOperatorThreadRow extends SupportThreadResponse {
  unread?: number
}

export interface SupportOperatorQueueResponse {
  threads: SupportOperatorThreadRow[]
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
 * POST /api/v1/support/threads/messages -- send one message into the
 * caller's own conversation. No thread id on the wire.
 *
 * 404 if the caller has never opened the channel (open first).
 */
export function sendSupportMessage(body: SendMessageIn['body']): Promise<SupportMessageResponse> {
  const payload: SendMessageIn = { body }
  return api.post<SupportMessageResponse>('/api/v1/support/threads/messages', payload)
}

/**
 * GET /api/v1/support/threads/{id}/messages -- that thread's feed,
 * newest first, keyset-paginated.
 *
 * 404 if `thread_id` is not this caller's (including a real thread
 * belonging to somebody else -- existence never leaks).
 */
export function getSupportThreadMessages(
  threadId: string,
  params?: ListMessagesParams,
): Promise<SupportMessageListResponse> {
  const qs = buildQueryString({
    limit: params?.limit,
    cursor: params?.cursor,
  })
  return api.get<SupportMessageListResponse>(`/api/v1/support/threads/${threadId}/messages${qs}`)
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
 * Backend strips the `claimed` flag comms returns and hands back only
 * the thread object -- a repeat claim by the SAME operator succeeds
 * (200) with the same payload, idempotent by construction. Claiming
 * one a colleague already took is 409, not a value in the body.
 */
export function claimStaffSupportThread(threadId: string): Promise<SupportThreadResponse> {
  const body: EmptyBodyIn = {}
  return api.post<SupportThreadResponse>(`/api/v1/staff/support/threads/${threadId}/claim`, body)
}

/**
 * GET /api/v1/staff/support/threads/{id}/messages -- read one known
 * request, newest first, keyset-paginated.
 *
 * SAME RESPONSE TYPE AS THE USER FEED, and that is a fact rather than
 * a convenience: both routes forward comms' `GET /threads/{id}/messages`
 * untouched (service.py get_support_messages and
 * get_operator_thread_messages), and comms builds that body from a
 * single serializer. Two types here would assert that one serializer
 * produces two shapes.
 *
 * 404 if the id names no support thread this product created. NOT
 * restricted to threads this operator claimed -- the queue shows the
 * unclaimed pool, and an operator reads a request before deciding to
 * take it. Claiming gates writing, not reading.
 */
export function getStaffSupportThreadMessages(
  threadId: string,
  params?: ListMessagesParams,
): Promise<SupportMessageListResponse> {
  const qs = buildQueryString({
    limit: params?.limit,
    cursor: params?.cursor,
  })
  return api.get<SupportMessageListResponse>(
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
): Promise<SupportMessageResponse> {
  const payload: SendMessageIn = { body }
  return api.post<SupportMessageResponse>(
    `/api/v1/staff/support/threads/${threadId}/messages`,
    payload,
  )
}

/**
 * POST /api/v1/staff/support/threads/{id}/status -- resolve or close.
 *
 * `open` is not a valid target (see SetStatusIn on the backend): a
 * closed thread revives only when the CLIENT writes into it, never
 * through this route.
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
