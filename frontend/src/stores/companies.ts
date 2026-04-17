// =============================================================================
// CBSHOME Frontend -- Companies Store (Phase F4.1 + F4.1.2 hotfix)
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
//
// F4.1.2 hotfix -- stale-epoch guard:
//   Without it, typing "Tesla" fast produces one in-flight request per
//   keystroke, and whichever resolves last wins -- which in network
//   reality is NOT the last one typed. Result: input shows "Tesla",
//   list shows results for "T". Now every call bumps a shared epoch;
//   stale resolves are dropped. The old `if (loading.value) return`
//   guard (which was what caused this, by silently eating valid new
//   calls) is gone.
//
//   UI-level debouncing still lives where it belongs -- in the
//   component, not in the store. See CompanyFilterSheet.vue which
//   debounces 250ms on the input before calling searchCompanies.
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

  // Epoch for stale-resolve detection -- see file header.
  let fetchEpoch = 0

  /**
   * Re-fetch companies for the given search string. Empty string
   * returns the most recent companies (no search filter applied).
   * Replaces items -- search narrows the whole result set, it does
   * not paginate.
   */
  async function searchCompanies(query: string): Promise<void> {
    const epoch = ++fetchEpoch
    loading.value = true
    error.value = null
    // Update search reactively up-front so the input reflects the
    // committed query even while the fetch is in flight.
    search.value = query
    try {
      const trimmed = query.trim()
      const resp = await listCompanies({
        search: trimmed ? trimmed : undefined,
        page: 1,
        per_page: PER_PAGE,
      })
      if (epoch !== fetchEpoch) return
      items.value = resp.items
      total.value = resp.total
    } catch (err) {
      if (epoch !== fetchEpoch) return
      error.value =
        err instanceof Error ? err.message : 'Failed to load companies'
    } finally {
      if (epoch === fetchEpoch) loading.value = false
    }
  }

  function reset(): void {
    // Invalidate any in-flight fetches so they don't write to the
    // store after reset().
    ++fetchEpoch
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
