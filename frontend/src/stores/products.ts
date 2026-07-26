// =============================================================================
// AIVIS.ONE Frontend -- Products Store (Phase F4.1 + F4.1.2 hotfix)
// =============================================================================
//
// Pinia store backing the Investor storefront (MarketView).
//
// SHAPE:
//   items              -- products currently in the grid (append on loadMore)
//   total              -- total matching the current filter (from server)
//   page               -- current page number (1-based)
//   companyIdFilter    -- optional company filter (null = all companies)
//   loading / error    -- UI flags
//   hasMore            -- items.length < total
//
// ACTIONS:
//   fetchFirstPage()       -- load page 1, REPLACE items
//   loadMore()             -- load next page, APPEND items
//   setCompanyFilter(id)   -- change filter + fetch first page
//   reset()                -- clear store state (on view unmount / logout)
//
// PAGINATION STRATEGY:
//   Infinite scroll -- items grow as the user scrolls via
//   composables/usePagination.ts (IntersectionObserver on a sentinel).
//   per_page fixed at 20 to match backend's default list size.
//
// F4.1.2 hotfix -- stale-epoch guard:
//   Every network-touching action bumps a shared `fetchEpoch`
//   counter and captures its own epoch. On resolve/reject it writes
//   to the store only if its epoch is still current. This kills
//   three race scenarios:
//     (a) user changes filter mid-fetch -- old resolve would have
//         overwritten items with pre-filter data,
//     (b) user calls fetchFirstPage again (e.g. retry) mid-fetch --
//         old resolve would double-write,
//     (c) loadMore in flight when filter changes -- old resolve
//         would APPEND stale items onto the new first page.
//   fetchFirstPage and loadMore share the same counter on purpose:
//   a filter change must invalidate any in-flight loadMore too.
//   The old `if (loading.value) return` guard was removed -- it
//   was the cause of (a), silently dropping the valid new call.
// =============================================================================

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { listProducts } from '@/api/products'
import type { PublicProductResponse } from '@/api/types'

const PER_PAGE = 20

export const useProductsStore = defineStore('products', () => {
  const items = ref<PublicProductResponse[]>([])
  const total = ref(0)
  const page = ref(1)
  const companyIdFilter = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const hasMore = computed(() => items.value.length < total.value)

  // Shared epoch counter. Plain `let` inside the setup factory is fine:
  // Pinia instantiates the store once per app, so this closure lives
  // for the entire app lifetime.
  let fetchEpoch = 0

  /**
   * Load page 1 and REPLACE items. Called on initial mount, when the
   * company filter changes, or to recover from an error.
   */
  async function fetchFirstPage(): Promise<void> {
    const epoch = ++fetchEpoch
    loading.value = true
    error.value = null
    try {
      const resp = await listProducts({
        company_id: companyIdFilter.value ?? undefined,
        page: 1,
        per_page: PER_PAGE,
      })
      // Discard stale resolve: a newer call bumped the epoch.
      if (epoch !== fetchEpoch) return
      items.value = resp.items
      total.value = resp.total
      page.value = 1
    } catch (err) {
      if (epoch !== fetchEpoch) return
      error.value =
        err instanceof Error ? err.message : 'Failed to load products'
    } finally {
      // Only clear the loading flag if we're the current epoch -- a
      // newer call already set loading=true and owns the lifecycle.
      if (epoch === fetchEpoch) loading.value = false
    }
  }

  /**
   * Load the next page and APPEND to items. Shares the epoch counter
   * with fetchFirstPage so that a filter change while loadMore is in
   * flight causes the old append to be discarded (see scenario (c)
   * in the header).
   */
  async function loadMore(): Promise<void> {
    if (!hasMore.value) return
    const epoch = ++fetchEpoch
    loading.value = true
    error.value = null
    const nextPage = page.value + 1
    try {
      const resp = await listProducts({
        company_id: companyIdFilter.value ?? undefined,
        page: nextPage,
        per_page: PER_PAGE,
      })
      if (epoch !== fetchEpoch) return
      items.value = [...items.value, ...resp.items]
      total.value = resp.total
      page.value = nextPage
    } catch (err) {
      if (epoch !== fetchEpoch) return
      error.value =
        err instanceof Error ? err.message : 'Failed to load more products'
    } finally {
      if (epoch === fetchEpoch) loading.value = false
    }
  }

  /**
   * Switch filter and re-fetch from page 1. No-op if the filter is
   * already set to the same value.
   *
   * Normalises empty / whitespace-only strings to null so callers
   * that emit '' instead of null (e.g. a cleared <select>) end up
   * with canonical state rather than a sneakily-truthy empty string
   * that the API wrapper would then drop silently.
   */
  async function setCompanyFilter(id: string | null): Promise<void> {
    const normalized = id && id.trim() ? id : null
    if (companyIdFilter.value === normalized) return
    companyIdFilter.value = normalized
    await fetchFirstPage()
  }

  function reset(): void {
    // Invalidate any in-flight fetches so they don't write to the
    // store after reset().
    ++fetchEpoch
    items.value = []
    total.value = 0
    page.value = 1
    companyIdFilter.value = null
    loading.value = false
    error.value = null
  }

  return {
    items,
    total,
    page,
    companyIdFilter,
    loading,
    error,
    hasMore,
    fetchFirstPage,
    loadMore,
    setCompanyFilter,
    reset,
  }
})
