// =============================================================================
// CBSHOME Frontend -- Portfolio Store (Phase F4.4 B1)
// =============================================================================
//
// Pinia store for the investor portfolio. Drives PortfolioView
// (top-level positions list) and CompanyPositionView (per-company
// aggregate + paginated purchases).
//
// STATE MODEL.
//   positions                 -- top-level list from GET /portfolio/me
//   positionsLoaded           -- "fetched at least once successfully"
//                                so tab-return can show stale data
//                                while a silent refresh is in flight
//   positionsLoading / errored
//
//   currentCompanyId          -- selected company, null when no detail view open
//   currentDetail             -- aggregate block for that company
//   currentPurchases          -- accumulated across detail pages
//   currentPage / currentTotal -- pagination watermarks
//   currentLoading / errored
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
//   worse than a brief spinner. If F6.x ever needs a cache, add a
//   Map<companyId, ...> alongside; the epoch-guard here won't fight
//   it.
//
// EPOCH GUARD.
//   A single counter shared across all three network paths
//   (fetchPortfolio, setCompanyId's detail load, loadMorePurchases).
//   Every path bumps it and captures the pre-bump value; resolves
//   whose captured value no longer matches are no-ops. Mirrors
//   stores/transactions.ts. One counter -- not per-path -- because
//   the only race that matters is "is this resolve still the
//   freshest one we care about"; separate counters would let a
//   portfolio refresh concurrently overwrite a newer company
//   detail fetch and vice versa, which is exactly the foot-gun we
//   want to preclude.
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

  // Shared epoch -- see header note on "one counter, not per-path".
  let fetchEpoch = 0

  const hasMoreCurrentPurchases = computed<boolean>(
    () => currentPurchases.value.length < currentTotal.value,
  )

  // -------------------------------------------------------------------------
  // Top-level portfolio
  // -------------------------------------------------------------------------

  async function fetchPortfolio(): Promise<void> {
    const epoch = ++fetchEpoch
    positionsLoading.value = true
    positionsErrored.value = false
    try {
      const resp = await getMyPortfolio()
      if (epoch !== fetchEpoch) return
      positions.value = resp.positions
      positionsLoaded.value = true
    } catch {
      if (epoch !== fetchEpoch) return
      positionsErrored.value = true
    } finally {
      if (epoch === fetchEpoch) {
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
   * epoch cancels any in-flight request against the previous id.
   */
  async function setCompanyId(id: string): Promise<void> {
    const epoch = ++fetchEpoch
    currentCompanyId.value = id
    currentDetail.value = null
    currentPurchases.value = []
    currentPage.value = 1
    currentTotal.value = 0
    currentLoading.value = true
    currentErrored.value = false
    try {
      const resp = await getCompanyPosition(id, {
        page: 1,
        per_page: PER_PAGE,
      })
      if (epoch !== fetchEpoch) return
      // Detail carries both the aggregate AND the first page of
      // purchases; splitting storage lets loadMorePurchases append
      // without cloning the aggregate.
      currentDetail.value = resp
      currentPurchases.value = resp.purchases
      currentTotal.value = resp.total
      currentPage.value = resp.page
    } catch {
      if (epoch !== fetchEpoch) return
      currentErrored.value = true
    } finally {
      if (epoch === fetchEpoch) {
        currentLoading.value = false
      }
    }
  }

  async function loadMorePurchases(): Promise<void> {
    if (
      currentCompanyId.value === null ||
      currentLoading.value ||
      !hasMoreCurrentPurchases.value
    ) {
      return
    }
    const id = currentCompanyId.value
    const epoch = ++fetchEpoch
    currentLoading.value = true
    try {
      const nextPage = currentPage.value + 1
      const resp = await getCompanyPosition(id, {
        page: nextPage,
        per_page: PER_PAGE,
      })
      if (epoch !== fetchEpoch) return
      // Silent drop if company switched mid-flight: the currentCompanyId
      // check above + the epoch guard together cover every race we
      // can construct today.
      if (currentCompanyId.value !== id) return
      currentPurchases.value = [
        ...currentPurchases.value,
        ...resp.purchases,
      ]
      currentTotal.value = resp.total
      currentPage.value = resp.page
      // Aggregate refresh is a happy side-effect: the detail response
      // recomputes current_value_cents against live company price,
      // so even a second-page load keeps the header honest without
      // a second round-trip.
      currentDetail.value = resp
    } catch {
      // Non-destructive, matches stores/transactions.loadMore. The
      // already-loaded pages stay visible; the user can tap Retry
      // on the first-page empty state if the initial call failed,
      // or just scroll and try again (infinite-scroll sentinel
      // will re-fire).
    } finally {
      if (epoch === fetchEpoch) {
        currentLoading.value = false
      }
    }
  }

  /**
   * Clear per-company state when the detail view unmounts. Bumps
   * the epoch so any in-flight fetch for this company resolves to
   * a no-op. The positions list is untouched -- it belongs to the
   * parent tab, not to the detail view.
   */
  function clearCurrent(): void {
    fetchEpoch++
    currentCompanyId.value = null
    currentDetail.value = null
    currentPurchases.value = []
    currentPage.value = 1
    currentTotal.value = 0
    currentLoading.value = false
    currentErrored.value = false
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
    hasMoreCurrentPurchases,
    setCompanyId,
    loadMorePurchases,
    clearCurrent,
  }
})
