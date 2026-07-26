// =============================================================================
// AIVIS.ONE Frontend -- Company Dashboard Store (Phase F5.1)
// =============================================================================
//
// Pinia store wrapping the single-payload company dashboard endpoint
// (GET /api/v1/company/dashboard). Drives CompanyDashboardView in
// F5.1 and is also consumed by CompanyBalanceView in F5.2 -- the
// passive_balance block lives in this same payload, so the balance
// view reuses the cached summary instead of calling the endpoint
// twice.
//
// STATE.
//   summary  -- CompanyDashboardResponse | null. Null is the
//               pre-fetch sentinel; views render a spinner or a
//               zeroed placeholder until `loading` flips false on
//               the first successful refresh.
//   loading  -- true during refresh()
//   error    -- last refresh error message, null on success
//
// PAYLOAD CONTENTS (mirrored from
//   backend/app/modules/company_dashboard/router.py, Sprint 4.3 B5,
//   Sprint 4.6 hotfix):
//     - passive_balance        BalanceResponse (confirmed + frozen)
//     - total_revenue_cents
//     - total_options_sold     sale + installment_tranche units
//     - products_count
//     - pool                   active OptionPool snapshot or `null`
//                              when staff has not created a pool yet
//     - recent_transactions    last 20 transactions, newest first
//
// EMBEDDED LIST DESIGN.
//   recent_transactions is part of the dashboard payload by design.
//   Views MUST NOT issue a second GET /transactions just to render
//   this widget. If the user tabs over to a full transactions list,
//   that list belongs to a separate (future) company-transactions
//   view with its own paginated store.
//
// REFRESH SEMANTICS.
//   refresh() always re-fetches. Unlike companyProfile (cache-first
//   loadIfMissing), the dashboard exposes balances and counters that
//   move with every purchase / withdrawal -- a stale cache here is
//   actively misleading. Views call refresh() in onMounted and may
//   call it again on Retry or after a withdrawal completes.
//
// RACE POLICY -- FP-17 EPOCH GUARD.
//   Identical to stores/dashboard.ts (investor side). A second
//   refresh() that starts before the first resolves supersedes it,
//   the loser's result is dropped, and only the latest winner
//   writes to summary / error / loading. reset() also bumps the
//   epoch so a refresh that lands after logout cannot repopulate
//   summary behind the guard.
// =============================================================================

import { ref } from 'vue'
import { defineStore } from 'pinia'

import { getCompanyDashboard } from '@/api/company'
import type { CompanyDashboardResponse } from '@/api/types'

export const useCompanyDashboardStore = defineStore('companyDashboard', () => {
  const summary = ref<CompanyDashboardResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Monotonic counter. Bumped by refresh() (on start) and reset()
  // (to invalidate any in-flight refresh). Non-reactive by design
  // -- only read inside the async closure after await points.
  let epoch = 0

  /**
   * Pull /company/dashboard and overwrite state.
   *
   * Never throws -- errors are captured on `error`. Callers that
   * need to branch on success should check `error` after
   * `await refresh()`.
   *
   * Epoch-guarded: a second refresh() that starts before the first
   * resolves will supersede the first -- the loser's result is
   * dropped silently, and only the latest winner writes to summary
   * / error / loading.
   */
  async function refresh(): Promise<void> {
    const mine = ++epoch
    loading.value = true
    error.value = null
    try {
      const next = await getCompanyDashboard()
      if (mine !== epoch) return
      summary.value = next
    } catch (err) {
      if (mine !== epoch) return
      error.value = err instanceof Error ? err.message : 'Unknown error'
    } finally {
      if (mine === epoch) {
        loading.value = false
      }
    }
  }

  /**
   * Reset state. Called on logout and role switch.
   *
   * Bumps epoch so any in-flight refresh() that resolves AFTER
   * reset() cannot repopulate summary -- a post-logout fetch coming
   * back with the previous user's data would otherwise overwrite
   * the cleared state.
   */
  function reset(): void {
    epoch += 1
    summary.value = null
    loading.value = false
    error.value = null
  }

  return {
    summary,
    loading,
    error,
    refresh,
    reset,
  }
})
