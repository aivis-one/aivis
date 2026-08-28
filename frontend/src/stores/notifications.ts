// =============================================================================
// AIVIS.ONE Frontend -- Notifications Store (Phase 6, the bell)
// =============================================================================
//
// Pinia store backing the header bell (CHeader.vue) and the inbox
// screen it opens (views/investor/NotificationsInboxView.vue, reused
// across all four authenticated shells the same way PortfolioView /
// InvestorEventsView already are -- see router/index.ts).
//
// TWO INDEPENDENT SURFACES, TWO EPOCHS (same FP-17 pattern as
// stores/support.ts's threadEpoch/queueEpoch split).
//   `unreadEpoch` guards ONLY the badge fetch (fetchUnreadCount,
//   called once on mount and then on a poll timer). `itemsEpoch`
//   guards the paginated feed (fetchFirstPage/loadMore). Sharing one
//   epoch would mean a background badge poll could silently discard
//   an in-flight loadMore() the inbox screen is waiting on, and vice
//   versa -- two screens' worth of state living in one store, exactly
//   the reason support.ts keeps its two groups apart.
//
//   BUT `unreadCount` ITSELF IS WRITTEN FROM FIVE PLACES, NOT ONE
//   (fetchUnreadCount, fetchFirstPage, loadMore, markRead,
//   markAllRead) -- an adversarial review caught the gap the original
//   two-epoch split left open: only fetchUnreadCount-vs-fetchUnreadCount
//   was ordered. A slow 45s-poll response in flight when the user taps
//   "mark all read" could land AFTER markAllRead's fresher write and
//   stomp the badge back to the pre-mark count, even though every row
//   is correctly shown as read. Fix: every non-poll writer also bumps
//   `unreadEpoch`, so a poll response that was in flight before the
//   mark action is discarded by its own epoch check on arrival --
//   the SAME mechanism, just applied to every writer of this field,
//   not only to the poll's own re-entrancy.
//
// POLLING LIVES HERE, NOT IN CHeader.vue.
//   There is no existing periodic-refresh precedent in this codebase
//   (dashboardStore.refresh() is call-it-yourself, fired from
//   onMounted / a retry button, never on a timer) so this store adds
//   the first one. Putting start/stopPolling as store actions rather
//   than a raw setInterval inline in CHeader keeps the interval id
//   and the "am I already polling" guard next to the state it
//   updates, and makes stopPolling() reachable from reset() too (a
//   session boundary that fires mid-poll must not leave a timer
//   writing into a store a logged-out screen no longer reads).
//   INTERVAL: 45s -- inside the 30-60s range a passive badge can
//   tolerate without hammering the endpoint (brief's own guidance);
//   picked at the midpoint since there's no existing per-feature
//   budget to read off.
//
// OPTIMISTIC MARK-READ.
//   markRead / markAllRead flip `read_at` on the local rows and
//   subtract from `unreadCount` before the request resolves is NOT
//   done here -- unlike support.ts's read receipts (which are fired
//   fully in the background, stake D), a mark-read here is a visible
//   tap target on the inbox screen and the response body already
//   carries the authoritative fresh count in the SAME round trip
//   (comms computes it inside the write transaction -- see comms'
//   inbox.py header). So both actions await the response and then
//   write `unreadCount` and the row's `read_at` from what the backend
//   actually confirmed, not from a guess -- cheap because there is
//   nothing to reconcile if the guess had been wrong.
// =============================================================================

import { reactive, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  getUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '@/api/notifications'
import type { NotificationItemOut } from '@/api/generated'

const POLL_INTERVAL_MS = 45_000

export const useNotificationsStore = defineStore('notifications', () => {
  // ---------------------------------------------------------------------
  // Badge
  // ---------------------------------------------------------------------
  const unreadCount = ref<number>(0)
  const unreadLoaded = ref<boolean>(false)

  let unreadEpoch = 0
  let pollTimer: ReturnType<typeof setInterval> | null = null

  async function fetchUnreadCount(): Promise<void> {
    const epoch = ++unreadEpoch
    try {
      const resp = await getUnreadNotificationCount()
      if (epoch !== unreadEpoch) return
      unreadCount.value = resp.unread
      unreadLoaded.value = true
    } catch {
      // A passive badge: a failed poll leaves the last known count on
      // screen rather than resetting to 0 (which would read as "all
      // read" when the truth is "we don't know right now"). Silent by
      // design -- see notifications/service.py's header on why comms
      // being briefly unreachable is not surfaced as a UI error for
      // this particular surface.
    }
  }

  /** Idempotent: a second call while already polling is a no-op. */
  function startPolling(): void {
    if (pollTimer !== null) return
    void fetchUnreadCount()
    pollTimer = setInterval(() => void fetchUnreadCount(), POLL_INTERVAL_MS)
  }

  function stopPolling(): void {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  // ---------------------------------------------------------------------
  // Feed (the inbox screen)
  // ---------------------------------------------------------------------
  const items = ref<NotificationItemOut[]>([])
  const nextCursor = ref<string | null>(null)
  const itemsLoaded = ref<boolean>(false)
  const itemsLoading = ref<boolean>(false)
  const itemsError = ref<boolean>(false)
  const loadMoreError = ref<boolean>(false)

  // Per-delivery-id, not a single shared boolean: an adversarial review
  // caught that one global `marking` flag silently dropped a tap on a
  // SECOND, distinct item while the first item's mark-read request was
  // still in flight (no error, no feedback -- the tap just did nothing).
  // A reactive Set lets each row guard only its own request.
  const markingIds = reactive<Set<string>>(new Set())
  const markingAll = ref<boolean>(false)

  function isMarking(deliveryId: string): boolean {
    return markingIds.has(deliveryId)
  }

  let itemsEpoch = 0

  async function fetchFirstPage(): Promise<void> {
    const epoch = ++itemsEpoch
    itemsLoading.value = true
    itemsError.value = false
    loadMoreError.value = false
    try {
      const resp = await listNotifications({ limit: 20 })
      if (epoch !== itemsEpoch) return
      items.value = resp.items
      nextCursor.value = resp.next_cursor ?? null
      unreadCount.value = resp.unread
      ++unreadEpoch // discard any poll response still in flight -- see header
      unreadLoaded.value = true
      itemsLoaded.value = true
    } catch {
      if (epoch !== itemsEpoch) return
      itemsError.value = true
    } finally {
      if (epoch === itemsEpoch) {
        itemsLoading.value = false
      }
    }
  }

  async function loadMore(): Promise<void> {
    if (itemsLoading.value || loadMoreError.value || nextCursor.value === null) return
    const epoch = itemsEpoch
    itemsLoading.value = true
    try {
      const resp = await listNotifications({ limit: 20, cursor: nextCursor.value })
      if (epoch !== itemsEpoch) return
      items.value = [...items.value, ...resp.items]
      nextCursor.value = resp.next_cursor ?? null
      unreadCount.value = resp.unread
      ++unreadEpoch // discard any poll response still in flight -- see header
    } catch {
      // FP-16-style brake (mirrors BalanceView's withdrawal history):
      // stop the infinite-scroll observer from re-firing until the
      // user explicitly retries. Already-loaded pages stay visible.
      if (epoch === itemsEpoch) loadMoreError.value = true
    } finally {
      if (epoch === itemsEpoch) itemsLoading.value = false
    }
  }

  function retryLoadMore(): void {
    loadMoreError.value = false
    void loadMore()
  }

  /**
   * Mark one item read. Written from the backend's confirmed response,
   * not guessed -- see header. A second tap on an already-read item is
   * harmless: comms' mark-read is idempotent and the backend forwards
   * whatever fresh count it returns.
   */
  async function markRead(deliveryId: string): Promise<void> {
    if (markingIds.has(deliveryId)) return
    markingIds.add(deliveryId)
    try {
      const resp = await markNotificationRead(deliveryId)
      const row = items.value.find((item) => item.id === deliveryId)
      if (row && row.read_at === null) {
        row.read_at = new Date().toISOString()
      }
      unreadCount.value = resp.unread
      ++unreadEpoch // discard any poll response still in flight -- see header
    } catch {
      // Silent, same reasoning as support.ts stake D: a failed
      // read-receipt is not something the person can act on, and
      // surfacing it would teach distrust of an item that is still
      // sitting right there, readable, in the list.
    } finally {
      markingIds.delete(deliveryId)
    }
  }

  /** Mark every unread item read; updates every row plus the badge. */
  async function markAllRead(): Promise<void> {
    if (markingAll.value) return
    markingAll.value = true
    try {
      const resp = await markAllNotificationsRead()
      const now = new Date().toISOString()
      for (const item of items.value) {
        if (item.read_at === null) item.read_at = now
      }
      unreadCount.value = resp.unread
      ++unreadEpoch // discard any poll response still in flight -- see header
    } catch {
      // Same silence as markRead -- nothing actionable to show.
    } finally {
      markingAll.value = false
    }
  }

  // ---------------------------------------------------------------------
  // Session boundary
  // ---------------------------------------------------------------------

  /**
   * Wired into stores/sessionReset.ts. Stops the poll timer FIRST --
   * a timer left running after logout would keep writing a stale
   * unreadCount into a store the next signed-out screen doesn't read,
   * and would fire an authenticated request behind a session that no
   * longer exists.
   */
  function reset(): void {
    stopPolling()
    ++unreadEpoch
    ++itemsEpoch

    unreadCount.value = 0
    unreadLoaded.value = false

    items.value = []
    nextCursor.value = null
    itemsLoaded.value = false
    itemsLoading.value = false
    itemsError.value = false
    loadMoreError.value = false

    markingIds.clear()
    markingAll.value = false
  }

  return {
    // badge
    unreadCount,
    unreadLoaded,
    fetchUnreadCount,
    startPolling,
    stopPolling,

    // feed
    items,
    nextCursor,
    itemsLoaded,
    itemsLoading,
    itemsError,
    loadMoreError,
    fetchFirstPage,
    loadMore,
    retryLoadMore,

    // mark read
    markingIds,
    isMarking,
    markingAll,
    markRead,
    markAllRead,

    // session boundary
    reset,
  }
})
