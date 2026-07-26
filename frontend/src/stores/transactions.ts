// =============================================================================
// AIVIS.ONE Frontend -- Transactions Store (Phase F4.3 B3 + F4.4 B1-post + F5.1 B1)
// =============================================================================
//
// Pinia store for the investor transaction event log. Drives
// TransactionsView's category tabs, infinite scroll, and detail
// sheet navigation.
//
// STATE MODEL.
//   items              -- cumulative list across pages for the active tab
//   total              -- server-reported total count for the active filter
//   page               -- highest page number already appended to items
//   typeFilter         -- null (All) or trailing-colon prefix like
//                         "deposit:" that the backend expands via
//                         Transaction.type.startswith(...)
//   loading            -- true while any network call is in flight
//   errored            -- first-page load failed; UI shows retry
//   loadMoreErrored    -- loadMore failed on a non-first page (F4.4 B1-post).
//                         Acts as a brake for useInfiniteScroll so a
//                         transient error does not turn into a retry
//                         storm at the backend. Cleared explicitly by
//                         clearLoadMoreError() when the user taps Retry.
//
// EPOCH GUARD.
//   Tab switches abort in-flight requests by bumping an epoch
//   counter. Resolves from older fetches check-and-return before
//   touching state, so a slow first-page response for "Deposits"
//   cannot overwrite the fresh "Withdrawals" tab contents. Mirrors
//   stores/products.ts and BalanceView's payment history pattern.
//
// FILTER SEMANTICS.
//   typeFilter is stored as the raw prefix string ('deposit:' etc.)
//   or null for All. Passing it through to listTransactions as-is
//   works because the backend dispatches on a trailing ':'. Keeping
//   the raw value in state also makes tab-active matching a cheap
//   equality check in the view.
//
// RESET POLICY (F5.1 B1).
//   reset() bumps fetchEpoch (so any in-flight fetch resolves to a
//   no-op) then clears every public ref. Wired into
//   stores/sessionReset.ts which auth.ts._clearSession() and
//   useAvatar's transitions call -- user A's transaction rows cannot
//   bleed into user B's session in the same tab. The pre-existing
//   epoch guard alone was insufficient: nothing bumped fetchEpoch on
//   logout, so a mid-flight resolve would have written A's rows back
//   into a surviving store.
// =============================================================================

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { listTransactions } from '@/api/transactions'
import type { TransactionResponse } from '@/api/types'

const PER_PAGE = 20

export const useTransactionsStore = defineStore('transactions', () => {
  const items = ref<TransactionResponse[]>([])
  const total = ref(0)
  const page = ref(1)
  // null = All tab. Otherwise a trailing-colon prefix the backend
  // expands (e.g. 'deposit:' matches every deposit:* event type).
  const typeFilter = ref<string | null>(null)
  const loading = ref(false)
  const errored = ref(false)
  // Set when loadMore (not first page) hits a transient error.
  // Consumed by useInfiniteScroll to suppress further sentinel-driven
  // calls until the user taps Retry -- see store header.
  const loadMoreErrored = ref(false)

  // Epoch guard -- every network-touching path bumps this counter
  // and captures the current value. A captured value that no longer
  // matches the current counter on resolve means a newer call has
  // superseded this one, and state mutations are skipped.
  let fetchEpoch = 0

  const hasMore = computed<boolean>(() => items.value.length < total.value)

  async function fetchFirstPage(): Promise<void> {
    const epoch = ++fetchEpoch
    loading.value = true
    errored.value = false
    // First-page fetch is a fresh start -- clear any stale pause
    // from a previous loadMore failure so the sentinel can resume
    // once the page arrives.
    loadMoreErrored.value = false
    try {
      const resp = await listTransactions({
        page: 1,
        per_page: PER_PAGE,
        type: typeFilter.value ?? undefined,
      })
      if (epoch !== fetchEpoch) return
      items.value = resp.items
      total.value = resp.total
      page.value = 1
    } catch {
      if (epoch !== fetchEpoch) return
      errored.value = true
    } finally {
      if (epoch === fetchEpoch) {
        loading.value = false
      }
    }
  }

  async function loadMore(): Promise<void> {
    if (loading.value || !hasMore.value || loadMoreErrored.value) return
    const epoch = ++fetchEpoch
    loading.value = true
    try {
      const nextPage = page.value + 1
      const resp = await listTransactions({
        page: nextPage,
        per_page: PER_PAGE,
        type: typeFilter.value ?? undefined,
      })
      if (epoch !== fetchEpoch) return
      items.value = [...items.value, ...resp.items]
      total.value = resp.total
      page.value = nextPage
    } catch {
      // Set the brake flag. Already-loaded pages stay visible, the
      // infinite-scroll composable stops firing until the view
      // calls clearLoadMoreError() in response to a user Retry.
      // Guard with the epoch so an older resolve (tab just switched)
      // cannot paint a stale error onto the fresh state.
      if (epoch !== fetchEpoch) return
      loadMoreErrored.value = true
    } finally {
      if (epoch === fetchEpoch) {
        loading.value = false
      }
    }
  }

  /**
   * Clear the loadMore pause flag so the infinite-scroll sentinel
   * can fire again. Intended to be called from a Retry button in
   * the view; the button then typically calls loadMore() itself so
   * the user sees an immediate attempt rather than waiting for the
   * next intersect event. The composable also watches the flag
   * going from true to false and will fire if the sentinel is
   * already on-screen -- the explicit call and the watcher converge
   * on the same behaviour without duplicate fetches (the loadMore
   * guard on `loading` covers that race).
   */
  function clearLoadMoreError(): void {
    loadMoreErrored.value = false
  }

  async function setTypeFilter(next: string | null): Promise<void> {
    if (typeFilter.value === next) return
    typeFilter.value = next
    await fetchFirstPage()
  }

  /**
   * Reset every ref to its initial state. See "RESET POLICY" in the
   * file header.
   *
   * FP-17 ordering: bump epoch FIRST so any in-flight resolve drops
   * silently, then clear refs, then loading/errored last so a UI
   * watching `loading` doesn't race-paint against a partially-cleared
   * state.
   */
  function reset(): void {
    ++fetchEpoch
    items.value = []
    total.value = 0
    page.value = 1
    typeFilter.value = null
    loadMoreErrored.value = false
    loading.value = false
    errored.value = false
  }

  return {
    items,
    total,
    page,
    typeFilter,
    loading,
    errored,
    loadMoreErrored,
    hasMore,
    fetchFirstPage,
    loadMore,
    clearLoadMoreError,
    setTypeFilter,
    reset,
  }
})
