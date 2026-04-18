// =============================================================================
// CBSHOME Frontend -- Transactions Store (Phase F4.3 B3)
// =============================================================================
//
// Pinia store for the investor transaction event log. Drives
// TransactionsView's category tabs, infinite scroll, and detail
// sheet navigation.
//
// STATE MODEL.
//   items        -- cumulative list across pages for the active tab
//   total        -- server-reported total count for the active filter
//   page         -- highest page number already appended to items
//   typeFilter   -- null (All) or trailing-colon prefix like
//                   "deposit:" that the backend expands via
//                   Transaction.type.startswith(...)
//   loading      -- true while any network call is in flight
//   errored      -- first-page load failed; UI shows retry
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
    if (loading.value || !hasMore.value) return
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
      // Non-destructive: already-loaded pages stay visible; the user
      // can scroll back up and tap Retry on the error banner if the
      // first page itself failed. A silent swallow for loadMore
      // avoids flashing a global error over a working list.
    } finally {
      if (epoch === fetchEpoch) {
        loading.value = false
      }
    }
  }

  async function setTypeFilter(next: string | null): Promise<void> {
    if (typeFilter.value === next) return
    typeFilter.value = next
    await fetchFirstPage()
  }

  return {
    items,
    total,
    page,
    typeFilter,
    loading,
    errored,
    hasMore,
    fetchFirstPage,
    loadMore,
    setTypeFilter,
  }
})
