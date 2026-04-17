// =============================================================================
// CBSHOME Frontend -- Products Store (Phase F4.1)
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

  /**
   * Load page 1 and REPLACE items. Called on initial mount, when the
   * company filter changes, or to recover from an error.
   */
  async function fetchFirstPage(): Promise<void> {
    if (loading.value) return
    loading.value = true
    error.value = null
    try {
      const resp = await listProducts({
        company_id: companyIdFilter.value ?? undefined,
        page: 1,
        per_page: PER_PAGE,
      })
      items.value = resp.items
      total.value = resp.total
      page.value = 1
    } catch (err) {
      error.value =
        err instanceof Error ? err.message : 'Failed to load products'
    } finally {
      loading.value = false
    }
  }

  /**
   * Load the next page and APPEND to items. No-op if already loading
   * or there is nothing more to fetch.
   */
  async function loadMore(): Promise<void> {
    if (loading.value || !hasMore.value) return
    loading.value = true
    error.value = null
    const nextPage = page.value + 1
    try {
      const resp = await listProducts({
        company_id: companyIdFilter.value ?? undefined,
        page: nextPage,
        per_page: PER_PAGE,
      })
      items.value = [...items.value, ...resp.items]
      total.value = resp.total
      page.value = nextPage
    } catch (err) {
      error.value =
        err instanceof Error ? err.message : 'Failed to load more products'
    } finally {
      loading.value = false
    }
  }

  /**
   * Switch filter and re-fetch from page 1. No-op if the filter is
   * already set to the same value.
   */
  async function setCompanyFilter(id: string | null): Promise<void> {
    if (companyIdFilter.value === id) return
    companyIdFilter.value = id
    await fetchFirstPage()
  }

  function reset(): void {
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
