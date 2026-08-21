// =============================================================================
// AIVIS.ONE Frontend -- Support Store (Ф-1)
// =============================================================================
//
// Pinia store for the support/request channel. Feeds Ф-2 (the user's
// own thread) and Ф-3 (the operator's queue). No screen exists yet --
// this batch only proves the state shape works against the live
// backend; UI decisions (polling, optimistic append, layout) belong
// to those later deliveries.
//
// WHY ONE STORE, NOT TWO (per stores/portfolio.ts's own header, same
// question for a different pair of surfaces).
//   The user thread and the operator queue are conceptually distinct,
//   but the coupling is direct: an operator claiming a thread opens
//   the SAME conversation a user is writing into. Splitting would
//   need either a shared subscription between two stores or a
//   duplicated notion of "this thread", for state that together is
//   still small. One store, two clearly separated sections.
//
// WHY PER-THREAD FLAGS ON THE OPERATOR SIDE, NOT ONE FLAG PER VERB.
//   The queue is a LIST of conversations. A single `claiming: boolean`
//   would light up every row's spinner (or every row's error banner)
//   the moment any ONE claim was in flight -- exactly the class of bug
//   a shared counter caused in portfolio.ts before it was split into
//   two epochs (see that file's header). Here the fan-out is wider
//   (N rows, not two code paths), so the fix is a map keyed by thread
//   id rather than a second boolean. This goes one level deeper than
//   the handoff's "each surface has its own flags" -- the operator
//   surface is itself many independent rows, and each needs its own.
//
// ERROR SHAPE: `{ message, status } | null`, never a bare boolean.
//   A 502/504 (comms unreachable) is a NORMAL backend answer, not a
//   frontend fault -- see app/core/comms.py comms_request docstring.
//   Carrying `status` lets a screen tell "support is temporarily down"
//   (502/504) apart from "you can't do that yet" (404/409) without
//   this store inventing a second vocabulary on top of ApiResponseError.
//   `message` is the backend's own text (already extracted by
//   api/client.ts), never re-worded here.
//
// NO OPTIMISTIC MUTATION ON SEND (see gate, stake D).
//   The feed is comms' own order ("newest first"), and this store does
//   not know -- and must not guess -- which end of the local array
//   that corresponds to for whichever screen ends up rendering it. A
//   successful send updates `lastSentMessage` and nothing else; the
//   caller re-fetches the page it cares about. Guessing "front" or
//   "back" would look fine at three messages and misorder at thirty.
//
// EPOCH GUARDS (same FP-17 pattern as portfolio.ts / transactions.ts).
//   Two independent counters: `threadEpoch` for the user-thread group
//   (open / list / messages / send / read), `queueEpoch` for the
//   operator queue LIST fetch only. Per-thread operator actions
//   (claim / reply / status) are guarded by their own in-flight map
//   instead of an epoch -- there is no "stale superseded call" for an
//   action keyed by thread id the way there is for a single list or
//   detail fetch; the in-flight flag already prevents a second click
//   from racing the first.
// =============================================================================

import { reactive, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  claimStaffSupportThread,
  getSupportThreadMessages,
  listStaffSupportQueue,
  listSupportThreads,
  markSupportThreadRead,
  openSupportThread,
  replyToStaffSupportThread,
  sendSupportMessage,
  setStaffSupportThreadStatus,
} from '@/api/support'
import { ApiResponseError } from '@/api/client'
import type {
  SupportMessageResponse,
  SupportOperatorThreadRow,
  SupportThreadListItem,
  SupportThreadResponse,
} from '@/api/support'
import type { SetStatusIn } from '@/api/generated'

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

export const useSupportStore = defineStore('support', () => {
  // ---------------------------------------------------------------------
  // User side -- the caller's own thread
  // ---------------------------------------------------------------------
  const thread = ref<SupportThreadResponse | null>(null)
  const threadLoading = ref<boolean>(false)
  const threadError = ref<SupportActionError | null>(null)

  const threads = ref<SupportThreadListItem[]>([])
  const threadsLoaded = ref<boolean>(false)
  const threadsLoading = ref<boolean>(false)
  const threadsError = ref<SupportActionError | null>(null)

  const messages = ref<SupportMessageResponse[]>([])
  const messagesNextCursor = ref<string | null>(null)
  const messagesLoading = ref<boolean>(false)
  const messagesError = ref<SupportActionError | null>(null)

  // Set on a successful send, cleared the moment a new send starts.
  // Not appended into `messages` -- see header, stake D.
  const lastSentMessage = ref<SupportMessageResponse | null>(null)
  const sending = ref<boolean>(false)
  const sendError = ref<SupportActionError | null>(null)

  const marking = ref<boolean>(false)
  const markError = ref<SupportActionError | null>(null)

  let threadEpoch = 0

  /**
   * Open (or re-open) the caller's conversation. Safe to call
   * repeatedly -- comms returns the same thread every time.
   */
  async function openThread(): Promise<void> {
    const epoch = ++threadEpoch
    threadLoading.value = true
    threadError.value = null
    try {
      const resp = await openSupportThread()
      if (epoch !== threadEpoch) return
      thread.value = resp
    } catch (err) {
      if (epoch !== threadEpoch) return
      threadError.value = toActionError(err)
    } finally {
      if (epoch === threadEpoch) {
        threadLoading.value = false
      }
    }
  }

  /**
   * The caller's own thread list. Rows without `unread` (comms was
   * unreachable, or the row is otherwise not counted) are a normal
   * result, not surfaced as `threadsError` -- see api/support.ts.
   */
  async function fetchThreads(): Promise<void> {
    const epoch = ++threadEpoch
    threadsLoading.value = true
    threadsError.value = null
    try {
      const resp = await listSupportThreads()
      if (epoch !== threadEpoch) return
      threads.value = resp.threads
      threadsLoaded.value = true
    } catch (err) {
      if (epoch !== threadEpoch) return
      threadsError.value = toActionError(err)
    } finally {
      if (epoch === threadEpoch) {
        threadsLoading.value = false
      }
    }
  }

  /**
   * First page (or a fresh reload) of the caller's own thread feed.
   */
  async function fetchMessages(threadId: string): Promise<void> {
    const epoch = ++threadEpoch
    messagesLoading.value = true
    messagesError.value = null
    try {
      const resp = await getSupportThreadMessages(threadId)
      if (epoch !== threadEpoch) return
      messages.value = resp.messages
      messagesNextCursor.value = resp.next_cursor
    } catch (err) {
      if (epoch !== threadEpoch) return
      messagesError.value = toActionError(err)
    } finally {
      if (epoch === threadEpoch) {
        messagesLoading.value = false
      }
    }
  }

  /**
   * Send one message into the caller's own conversation.
   *
   * `sendError` is cleared at the start and set only on a real
   * failure -- so "not yet attempted" and "attempted and failed" are
   * distinguishable by (`sendError === null` vs not) the same way
   * "attempted and succeeded" is by `lastSentMessage`. A 404 here
   * means the channel was never opened; the caller should route back
   * to `openThread`, this store does not auto-open on their behalf
   * (see service.py -- auto-opening was rejected there for the same
   * reason: it would hide which of the two calls failed).
   */
  async function sendMessage(body: string): Promise<void> {
    sending.value = true
    sendError.value = null
    lastSentMessage.value = null
    try {
      const resp = await sendSupportMessage(body)
      lastSentMessage.value = resp
    } catch (err) {
      sendError.value = toActionError(err)
    } finally {
      sending.value = false
    }
  }

  /**
   * Mark the caller's thread read; updates the open thread's row in
   * `threads` if present, so a badge reflects the fresh count without
   * a full re-fetch.
   */
  async function markRead(threadId: string): Promise<void> {
    marking.value = true
    markError.value = null
    try {
      const resp = await markSupportThreadRead(threadId)
      const row = threads.value.find((t) => t.id === threadId)
      if (row) {
        row.unread = resp.unread
      }
    } catch (err) {
      markError.value = toActionError(err)
    } finally {
      marking.value = false
    }
  }

  // ---------------------------------------------------------------------
  // Staff side -- the operator's queue
  // ---------------------------------------------------------------------
  const queue = ref<SupportOperatorThreadRow[]>([])
  const queueNextCursor = ref<string | null>(null)
  const queueLoaded = ref<boolean>(false)
  const queueLoading = ref<boolean>(false)
  const queueError = ref<SupportActionError | null>(null)

  // Per-thread in-flight + error maps -- see header on why a single
  // flag per verb would misrepresent a list of independent rows.
  const claiming = reactive<Record<string, boolean>>({})
  const claimErrors = reactive<Record<string, SupportActionError | null>>({})

  const replying = reactive<Record<string, boolean>>({})
  const replyErrors = reactive<Record<string, SupportActionError | null>>({})

  const changingStatus = reactive<Record<string, boolean>>({})
  const statusErrors = reactive<Record<string, SupportActionError | null>>({})

  let queueEpoch = 0

  async function fetchQueue(): Promise<void> {
    const epoch = ++queueEpoch
    queueLoading.value = true
    queueError.value = null
    try {
      const resp = await listStaffSupportQueue()
      if (epoch !== queueEpoch) return
      queue.value = resp.threads
      queueNextCursor.value = resp.next_cursor
      queueLoaded.value = true
    } catch (err) {
      if (epoch !== queueEpoch) return
      queueError.value = toActionError(err)
    } finally {
      if (epoch === queueEpoch) {
        queueLoading.value = false
      }
    }
  }

  function _replaceQueueRow(updated: SupportThreadResponse): void {
    const idx = queue.value.findIndex((t) => t.id === updated.id)
    if (idx !== -1) {
      // Preserve `unread` -- the write endpoints return the bare
      // _thread_out shape and never carry it (see api/support.ts).
      queue.value[idx] = { ...updated, unread: queue.value[idx].unread }
    }
  }

  /**
   * Claim an unclaimed request. A repeat claim by this same operator
   * is a success (idempotent); a 409 means a colleague won the race.
   * Guarded per thread id: a second click while the first is still in
   * flight is a no-op rather than a second request.
   */
  async function claimThread(threadId: string): Promise<void> {
    if (claiming[threadId]) return
    claiming[threadId] = true
    claimErrors[threadId] = null
    try {
      const resp = await claimStaffSupportThread(threadId)
      _replaceQueueRow(resp)
    } catch (err) {
      claimErrors[threadId] = toActionError(err)
    } finally {
      claiming[threadId] = false
    }
  }

  /**
   * Answer as this operator. A 409 (`support_thread_not_claimed`) is
   * the backend's way of saying "claim it first" -- surfaced as-is in
   * `replyErrors[threadId]`, not translated here.
   */
  async function replyToThread(threadId: string, body: string): Promise<void> {
    if (replying[threadId]) return
    replying[threadId] = true
    replyErrors[threadId] = null
    try {
      await replyToStaffSupportThread(threadId, body)
    } catch (err) {
      replyErrors[threadId] = toActionError(err)
    } finally {
      replying[threadId] = false
    }
  }

  /**
   * Resolve or close a thread. `open` is not offered as a target --
   * see SetStatusIn on the backend; there is no manual reopen.
   */
  async function setThreadStatus(
    threadId: string,
    status: SetStatusIn['status'],
  ): Promise<void> {
    if (changingStatus[threadId]) return
    changingStatus[threadId] = true
    statusErrors[threadId] = null
    try {
      const resp = await setStaffSupportThreadStatus(threadId, status)
      _replaceQueueRow(resp)
    } catch (err) {
      statusErrors[threadId] = toActionError(err)
    } finally {
      changingStatus[threadId] = false
    }
  }

  // ---------------------------------------------------------------------
  // Session boundary
  // ---------------------------------------------------------------------

  /**
   * Full reset, wired into stores/sessionReset.ts. Bumps both epochs
   * first so an in-flight fetch from either group cannot repopulate
   * cleared state after resolving (same FP-17 pattern as
   * portfolio.ts). Per-thread maps are cleared wholesale -- there is
   * no per-row epoch to guard them, but every in-flight action is for
   * a queue that is about to be dropped anyway, so a stale write into
   * a cleared object key is harmless (nothing reads it once the arrays
   * are empty and the screen has unmounted on logout).
   */
  function reset(): void {
    ++threadEpoch
    ++queueEpoch

    thread.value = null
    threadLoading.value = false
    threadError.value = null

    threads.value = []
    threadsLoaded.value = false
    threadsLoading.value = false
    threadsError.value = null

    messages.value = []
    messagesNextCursor.value = null
    messagesLoading.value = false
    messagesError.value = null

    lastSentMessage.value = null
    sending.value = false
    sendError.value = null

    marking.value = false
    markError.value = null

    queue.value = []
    queueNextCursor.value = null
    queueLoaded.value = false
    queueLoading.value = false
    queueError.value = null

    for (const key of Object.keys(claiming)) delete claiming[key]
    for (const key of Object.keys(claimErrors)) delete claimErrors[key]
    for (const key of Object.keys(replying)) delete replying[key]
    for (const key of Object.keys(replyErrors)) delete replyErrors[key]
    for (const key of Object.keys(changingStatus)) delete changingStatus[key]
    for (const key of Object.keys(statusErrors)) delete statusErrors[key]
  }

  return {
    // user thread
    thread,
    threadLoading,
    threadError,
    openThread,

    // user thread list
    threads,
    threadsLoaded,
    threadsLoading,
    threadsError,
    fetchThreads,

    // user message feed
    messages,
    messagesNextCursor,
    messagesLoading,
    messagesError,
    fetchMessages,

    // user send
    lastSentMessage,
    sending,
    sendError,
    sendMessage,

    // user read
    marking,
    markError,
    markRead,

    // operator queue
    queue,
    queueNextCursor,
    queueLoaded,
    queueLoading,
    queueError,
    fetchQueue,

    // operator per-thread actions
    claiming,
    claimErrors,
    claimThread,
    replying,
    replyErrors,
    replyToThread,
    changingStatus,
    statusErrors,
    setThreadStatus,

    // session boundary
    reset,
  }
})
