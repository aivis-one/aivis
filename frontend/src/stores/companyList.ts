// =============================================================================
// AIVIS.ONE Frontend -- Company List Store (iter 2.5 batch 4, R1 §1.2)
// =============================================================================
//
// Pinia store for the Investor "Companies" tab. Drives CompanyListView's
// infinite scroll (batch 5) over `/api/v1/public/companies` -- the
// public storefront list endpoint migrated in batch 1.
//
// Replaces the role of the now-superseded `stores/companies.ts` for
// the LIST CASE specifically. The legacy `companies.ts` was wired to
// CompanyFilterSheet's search-driven bottom-sheet inside the old
// MarketView; its semantics (`searchCompanies(query)` -> replace, no
// pagination) are wrong for an infinite-scroll list view. The legacy
// store stays in place for as long as the filter sheet does -- it gets
// removed alongside CompanyFilterSheet in batch 8.
//
// STATE MODEL.
//   items              -- cumulative list across pages
//   total              -- server-reported total count
//   page               -- highest page number already appended
//   loading            -- true while any network call is in flight
//   errored            -- first-page load failed; UI shows retry
//   loadMoreErrored    -- non-first-page failure (FP-16 retry-storm
//                         brake). useInfiniteScroll suppresses
//                         further sentinel-driven calls until the
//                         user taps Retry -> clearLoadMoreError().
//
// EPOCH GUARD (FP-17).
//   Every network-touching path bumps `fetchEpoch` and captures its
//   own epoch. A resolve whose epoch no longer matches the current
//   counter writes nothing -- a superseded fetch silently drops. This
//   covers: rapid logout + relogin, avatar swap, navigation-with-prop-
//   churn, reset() during an in-flight fetch. Same pattern as
//   stores/transactions.ts and stores/products.ts.
//
// RESET POLICY (F5.1 B1 carried forward).
//   reset() bumps fetchEpoch FIRST so any in-flight resolve drops
//   silently, then clears every public ref. Wired into
//   stores/sessionReset.ts which auth.ts._clearSession() and
//   useAvatar's transitions call. User A's company list cannot bleed
//   into user B's session in the same tab.
//
// NO SEARCH PARAM (intentional).
//   iter 2.5 R1 §1.2 specifies a vertical list of company cards with
//   infinite scroll, NO search box. If a search affordance is added
//   in a future iteration, plumb a `searchQuery: ref<string>` here +
//   normalise empty/whitespace as the products store does, and have
//   setQuery() short-circuit on equality before re-fetching.
//
// NO SEED FROM /companies LEGACY STORE.
//   The legacy store's items shape is identical (same backend DTO,
//   same denormalised fields) but its pagination state is unrelated
//   (per_page=50, no infinite scroll). Mixing the two would couple
//   batch 4 to the removal of batch 8. Each store does its own
//   fetchFirstPage on mount.
// =============================================================================

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { listCompanies } from '@/api/companies'
import type { PublicCompanyListResponse } from '@/api/types'

// Per-page fetch size. Matches transactions / portfolio / products
// stores for a consistent infinite-scroll cadence.
const PER_PAGE = 20

// Item type derived from the list response. Codegen names the item
// schema PublicCompanyResponse on the backend OpenAPI, but the only
// consumer (this store + CompanyListView) reaches it through the list
// container -- avoiding a separate re-export keeps api/types.ts lean.
type CompanyListItem = PublicCompanyListResponse['items'][number]

export const useCompanyListStore = defineStore('companyList', () => {
  const items = ref<CompanyListItem[]>([])
  const total = ref<number>(0)
  const page = ref<number>(1)
  const loading = ref<boolean>(false)
  const errored = ref<boolean>(false)
  // FP-16 brake -- set when a non-first-page fetch hits a transient
  // error. The view passes this into useInfiniteScroll as `paused` so
  // the IntersectionObserver stops firing until the user taps Retry.
  const loadMoreErrored = ref<boolean>(false)

  // Shared epoch counter. Plain `let` inside the setup factory is
  // fine: Pinia instantiates the store once per app, so this closure
  // lives for the entire app lifetime.
  let fetchEpoch = 0

  const hasMore = computed<boolean>(
    () => items.value.length < total.value,
  )

  /**
   * Load page 1 and REPLACE items. Called on initial mount, when the
   * view's Retry button fires, and from reset()-then-refresh
   * sequences after a session boundary.
   *
   * Also clears any stale loadMoreErrored from a previous list state
   * -- a fresh first page is a fresh start for the brake.
   */
  async function fetchFirstPage(): Promise<void> {
    const epoch = ++fetchEpoch
    loading.value = true
    errored.value = false
    loadMoreErrored.value = false
    try {
      const resp = await listCompanies({
        page: 1,
        per_page: PER_PAGE,
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

  /**
   * Load the next page and APPEND to items. Guarded against:
   *   - first-page-not-yet-loaded (page>=1 invariant ensured by
   *     fetchFirstPage being the only entry point)
   *   - in-flight load (loading.value)
   *   - exhausted list (!hasMore.value)
   *   - paused after error (loadMoreErrored.value, FP-16 brake)
   *
   * On non-first-page failure, sets loadMoreErrored instead of
   * errored -- already-loaded pages stay visible and the user gets
   * a row-level Retry banner instead of a full-page failure state.
   */
  async function loadMore(): Promise<void> {
    if (
      loading.value
      || !hasMore.value
      || loadMoreErrored.value
    ) {
      return
    }
    const epoch = ++fetchEpoch
    loading.value = true
    try {
      const nextPage = page.value + 1
      const resp = await listCompanies({
        page: nextPage,
        per_page: PER_PAGE,
      })
      if (epoch !== fetchEpoch) return
      items.value = [...items.value, ...resp.items]
      total.value = resp.total
      page.value = nextPage
    } catch {
      // Brake on: useInfiniteScroll stops firing until the user
      // taps Retry. Guard with the epoch so an older resolve
      // (a reset / re-mount race) cannot paint a stale error onto
      // a fresh state.
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
   * can fire again. Called by the view's Retry button; the button
   * typically also calls loadMore() so the user sees an immediate
   * attempt rather than waiting for the next intersect event. The
   * `loading` guard in loadMore() covers the duplicate-fetch race.
   */
  function clearLoadMoreError(): void {
    loadMoreErrored.value = false
  }

  /**
   * Full session reset. See "RESET POLICY" in the file header.
   *
   * FP-17 ordering: bump epoch FIRST so any in-flight resolve drops
   * silently, then clear refs, then loading/errored last so UI
   * watching `loading` doesn't race-paint against a partially
   * cleared state.
   */
  function reset(): void {
    ++fetchEpoch
    items.value = []
    total.value = 0
    page.value = 1
    loadMoreErrored.value = false
    loading.value = false
    errored.value = false
  }

  return {
    items,
    total,
    page,
    loading,
    errored,
    loadMoreErrored,
    hasMore,
    fetchFirstPage,
    loadMore,
    clearLoadMoreError,
    reset,
  }
})
