// =============================================================================
// AIVIS.ONE Frontend -- Portfolio Store (Phase F4.4 B1 + B1-post + F5.1 B1)
// =============================================================================
//
// Pinia store for the investor portfolio. Drives PortfolioView
// (top-level positions list) and CompanyPositionView (per-company
// aggregate + paginated purchases).
//
// STATE MODEL.
//   positions                  -- top-level list from GET /portfolio/me
//   positionsLoaded            -- "fetched at least once successfully"
//                                 so tab-return can show stale data
//                                 while a silent refresh is in flight
//   positionsLoading / errored
//
//   currentCompanyId           -- selected company, null when no detail open
//   currentDetail              -- aggregate block for that company
//   currentPurchases           -- accumulated across detail pages
//   currentPage / currentTotal -- pagination watermarks
//   currentLoading / errored
//   currentLoadMoreErrored     -- per-company loadMore failed on a non-first
//                                 page; brake for useInfiniteScroll so a
//                                 flaky network cannot stampede the backend
//
// WHY ONE STORE, NOT TWO.
//   Portfolio list (small, rarely refreshed) and per-company detail
//   (paginated, refreshed on navigation) are conceptually distinct,
//   but the coupling between them is trivial: tapping a position
//   opens a detail view for that company_id. Splitting into two
//   stores would require either a shared subscription or duplicated
//   clearCurrent logic -- more surface than the flat shape below.
//   This matches stores/transactions.ts (tabs + detail live in one
//   store) and the boss's instruction for F4.4.
//
// WHY NO PER-COMPANY CACHE.
//   Re-entering a company from the portfolio list re-fetches. The
//   tradeoff: ~200ms fresh-data penalty on navigation vs. avoiding
//   a cache-invalidation contract after every purchase in Market.
//   Companies are edited rarely but by a single owner, and purchases
//   change aggregate figures instantly -- a stale cache would be
//   worse than a brief spinner.
//
// TWO EPOCH COUNTERS (B1-post change).
//   B1 used a single shared counter across all network paths. That
//   was wrong: fetchPortfolio() writes only `positions*`, setCompanyId
//   and loadMorePurchases write only `current*`. Shared counter made
//   them invalidate each other without cause -- e.g. a fetchPortfolio
//   in flight while the user tapped a position left positionsLoading
//   pinned to true forever, because the finally clause's
//   `epoch === fetchEpoch` check failed after setCompanyId bumped.
//   Split into `portfolioEpoch` and `currentEpoch`: each path guards
//   only against its own peers, and the two groups no longer pretend
//   to race.
//
// PAUSE ON loadMore FAILURE (B1-post change).
//   currentLoadMoreErrored is set when a non-first-page fetch fails.
//   The consuming view passes this ref into useInfiniteScroll as the
//   `paused` parameter so the IntersectionObserver stops firing after
//   a failure. User-tapped Retry calls clearLoadMoreError() and, if
//   the sentinel is still on-screen, the composable re-fires once.
//
// RESET POLICY (F5.1 B1).
//   The store now exposes BOTH clearCurrent() and reset() because they
//   serve different scopes:
//     clearCurrent() -- view unmount of CompanyPositionView. Bumps
//                       only currentEpoch, clears only the `current*`
//                       group. Leaves the top-level positions list
//                       intact -- the parent tab still owns it.
//     reset()        -- session boundary (logout / 401 / avatar swap).
//                       Bumps BOTH epochs and clears EVERYTHING.
//                       Wired into stores/sessionReset.ts. The
//                       previously-existing epoch guard alone could
//                       not protect against logout because nothing
//                       ever bumped portfolioEpoch on a session drop
//                       -- a mid-flight fetchPortfolio() resolved
//                       after _clearSession() would write A's
//                       positions back into a surviving store.
// =============================================================================

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { getCompanyPosition, getMyPortfolio } from '@/api/portfolio'
import type {
  CompanyPositionDetailResponse,
  PortfolioPositionResponse,
  PurchaseItemResponse,
} from '@/api/types'

const PER_PAGE = 20

export const usePortfolioStore = defineStore('portfolio', () => {
  // -- Top-level positions list (GET /portfolio/me) --
  const positions = ref<PortfolioPositionResponse[]>([])
  const positionsLoaded = ref<boolean>(false)
  const positionsLoading = ref<boolean>(false)
  const positionsErrored = ref<boolean>(false)

  // -- Per-company detail (GET /portfolio/me/company/{id}) --
  const currentCompanyId = ref<string | null>(null)
  const currentDetail = ref<CompanyPositionDetailResponse | null>(null)
  const currentPurchases = ref<PurchaseItemResponse[]>([])
  const currentPage = ref<number>(1)
  const currentTotal = ref<number>(0)
  const currentLoading = ref<boolean>(false)
  const currentErrored = ref<boolean>(false)
  const currentLoadMoreErrored = ref<boolean>(false)

  // Two independent epoch counters. See header "TWO EPOCH COUNTERS".
  let portfolioEpoch = 0
  let currentEpoch = 0

  const hasMoreCurrentPurchases = computed<boolean>(
    () => currentPurchases.value.length < currentTotal.value,
  )

  // -------------------------------------------------------------------------
  // Top-level portfolio
  // -------------------------------------------------------------------------

  async function fetchPortfolio(): Promise<void> {
    const epoch = ++portfolioEpoch
    positionsLoading.value = true
    positionsErrored.value = false
    try {
      const resp = await getMyPortfolio()
      if (epoch !== portfolioEpoch) return
      positions.value = resp.positions
      positionsLoaded.value = true
    } catch {
      if (epoch !== portfolioEpoch) return
      positionsErrored.value = true
    } finally {
      if (epoch === portfolioEpoch) {
        positionsLoading.value = false
      }
    }
  }

  // -------------------------------------------------------------------------
  // Per-company detail
  // -------------------------------------------------------------------------

  /**
   * Select a company and load its first page of purchase detail.
   *
   * Idempotent: calling with the same id as `currentCompanyId` still
   * re-fetches, because the caller's trigger (usually onMounted of
   * CompanyPositionView) implies they want fresh data. Bumping the
   * currentEpoch cancels any in-flight request against the previous id.
   */
  async function setCompanyId(id: string): Promise<void> {
    const epoch = ++currentEpoch
    currentCompanyId.value = id
    currentDetail.value = null
    currentPurchases.value = []
    currentPage.value = 1
    currentTotal.value = 0
    currentLoading.value = true
    currentErrored.value = false
    // New company is a fresh start for the loadMore brake -- any
    // stale pause from the previous company must not block the
    // sentinel here.
    currentLoadMoreErrored.value = false
    try {
      const resp = await getCompanyPosition(id, {
        page: 1,
        per_page: PER_PAGE,
      })
      if (epoch !== currentEpoch) return
      // Detail carries both the aggregate AND the first page of
      // purchases; splitting storage lets loadMorePurchases append
      // without cloning the aggregate.
      currentDetail.value = resp
      currentPurchases.value = resp.purchases
      currentTotal.value = resp.total
      currentPage.value = resp.page
    } catch {
      if (epoch !== currentEpoch) return
      currentErrored.value = true
    } finally {
      if (epoch === currentEpoch) {
        currentLoading.value = false
      }
    }
  }

  async function loadMorePurchases(): Promise<void> {
    if (
      currentCompanyId.value === null ||
      currentLoading.value ||
      currentLoadMoreErrored.value ||
      !hasMoreCurrentPurchases.value
    ) {
      return
    }
    const id = currentCompanyId.value
    const epoch = ++currentEpoch
    currentLoading.value = true
    try {
      const nextPage = currentPage.value + 1
      const resp = await getCompanyPosition(id, {
        page: nextPage,
        per_page: PER_PAGE,
      })
      if (epoch !== currentEpoch) return
      // Silent drop if the company switched mid-flight -- the
      // currentCompanyId check plus the epoch guard together cover
      // every race we can construct.
      if (currentCompanyId.value !== id) return
      currentPurchases.value = [...currentPurchases.value, ...resp.purchases]
      currentTotal.value = resp.total
      currentPage.value = resp.page
      // Aggregate refresh is a happy side-effect: the detail response
      // recomputes current_value_cents against live company price,
      // so even a second-page load keeps the header honest without
      // a second round-trip.
      currentDetail.value = resp
    } catch {
      // Brake on: useInfiniteScroll stops firing until the user
      // taps Retry. Guard with the epoch so an older resolve
      // (company just switched) cannot paint a stale error onto
      // the fresh state.
      if (epoch !== currentEpoch) return
      currentLoadMoreErrored.value = true
    } finally {
      if (epoch === currentEpoch) {
        currentLoading.value = false
      }
    }
  }

  /**
   * Clear the per-company loadMore pause flag after a user Retry
   * interaction. Pairs with useInfiniteScroll's `paused` parameter
   * -- the composable watches the flag going from true to false
   * and, if the sentinel is still on-screen, fires loadMore once.
   * See stores/transactions.ts clearLoadMoreError for the same
   * contract on that store.
   */
  function clearLoadMoreError(): void {
    currentLoadMoreErrored.value = false
  }

  /**
   * Clear per-company state when the detail view unmounts. Bumps
   * currentEpoch so any in-flight fetch for this company resolves
   * to a no-op. Does not touch portfolioEpoch -- the positions list
   * belongs to the parent tab, not to the detail view.
   *
   * NOT a session-boundary reset. See `reset()` below for that.
   */
  function clearCurrent(): void {
    currentEpoch++
    currentCompanyId.value = null
    currentDetail.value = null
    currentPurchases.value = []
    currentPage.value = 1
    currentTotal.value = 0
    currentLoading.value = false
    currentErrored.value = false
    currentLoadMoreErrored.value = false
  }

  /**
   * Full session reset. See "RESET POLICY" in the file header.
   *
   * Bumps BOTH epochs first so any in-flight fetch in either group
   * (fetchPortfolio in the positions group, setCompanyId /
   * loadMorePurchases in the current-company group) drops silently
   * on resolve. Then clears both groups of refs.
   *
   * Wired into stores/sessionReset.ts.
   */
  function reset(): void {
    ++portfolioEpoch
    ++currentEpoch
    // positions group
    positions.value = []
    positionsLoaded.value = false
    positionsLoading.value = false
    positionsErrored.value = false
    // current-company group
    currentCompanyId.value = null
    currentDetail.value = null
    currentPurchases.value = []
    currentPage.value = 1
    currentTotal.value = 0
    currentLoading.value = false
    currentErrored.value = false
    currentLoadMoreErrored.value = false
  }

  return {
    // positions
    positions,
    positionsLoaded,
    positionsLoading,
    positionsErrored,
    fetchPortfolio,

    // current company
    currentCompanyId,
    currentDetail,
    currentPurchases,
    currentPage,
    currentTotal,
    currentLoading,
    currentErrored,
    currentLoadMoreErrored,
    hasMoreCurrentPurchases,
    setCompanyId,
    loadMorePurchases,
    clearLoadMoreError,
    clearCurrent,

    // session boundary
    reset,
  }
})
