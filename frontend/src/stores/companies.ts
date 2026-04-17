// =============================================================================
// CBSHOME Frontend -- Companies Store (Phase F4.1)
// =============================================================================
//
// Pinia store backing the Investor storefront company filter
// bottom-sheet (CompanyFilterSheet). Search-driven, not full catalogue
// dump -- at 500+ companies we never ship the whole list.
//
// SHAPE:
//   items        -- companies matching the current search (replaced,
//                   not appended -- search narrows, does not paginate)
//   total        -- total matches on the server (for "N results" label)
//   search       -- current search string (empty = show most recent)
//   loading / error
//
// ACTIONS:
//   searchCompanies(query)  -- re-fetch with given search string
//   reset()                 -- clear store state
//
// PAGE SIZE:
//   per_page = 50 -- larger than the storefront grid because the filter
//   sheet shows a compact list, and search usually narrows to a handful.
// =============================================================================

import { ref } from 'vue'
import { defineStore } from 'pinia'

import { listCompanies } from '@/api/companies'
import type { PublicCompanyResponse } from '@/api/types'

const PER_PAGE = 50

export const useCompaniesStore = defineStore('companies', () => {
  const items = ref<PublicCompanyResponse[]>([])
  const total = ref(0)
  const search = ref('')
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * Re-fetch companies for the given search string. Empty string
   * returns the most recent companies (no search filter applied).
   * Replaces items -- search narrows the whole result set, it does
   * not paginate.
   */
  async function searchCompanies(query: string): Promise<void> {
    if (loading.value) return
    loading.value = true
    error.value = null
    search.value = query
    try {
      const trimmed = query.trim()
      const resp = await listCompanies({
        search: trimmed ? trimmed : undefined,
        page: 1,
        per_page: PER_PAGE,
      })
      items.value = resp.items
      total.value = resp.total
    } catch (err) {
      error.value =
        err instanceof Error ? err.message : 'Failed to load companies'
    } finally {
      loading.value = false
    }
  }

  function reset(): void {
    items.value = []
    total.value = 0
    search.value = ''
    loading.value = false
    error.value = null
  }

  return {
    items,
    total,
    search,
    loading,
    error,
    searchCompanies,
    reset,
  }
})
