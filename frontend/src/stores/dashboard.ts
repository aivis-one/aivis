// =============================================================================
// CBSHOME Frontend -- Dashboard Store (Phase F4.4 B2)
// =============================================================================
//
// Pinia store exposing the full /api/v1/dashboard/summary payload to
// all investor screens that need it. Replaces `stores/balance.ts`
// (F4.3 B2) -- the F4.3 store only exposed the two ledger-balance
// blocks, callers that needed portfolio aggregates (total_invested,
// current_value, companies list) had to call the endpoint inline.
// F4.4 Dashboard needs the full payload, so the store grows to host
// it; the balance-only view (BalanceView) keeps working against the
// same store via `summary?.active_balance`.
//
// STATE (all amounts in USD cents):
//   summary    -- full DashboardSummaryResponse | null before first fetch.
//                 null is the pre-fetch sentinel; callers render a
//                 spinner or a zeroed placeholder until `loading`
//                 flips false.
//   loading    -- true during refresh()
//   error      -- last refresh error message, null on success
//
// CONVENIENCE GETTERS.
//   activeBalance / passiveBalance return the matching `BalanceResponse`
//   from the summary, or a zeroed placeholder when summary is null.
//   BalanceView / PurchaseView / InstallmentView call these directly
//   without guarding for null -- keeps the template blast radius the
//   same as the F4.3 store.
//
// ACTIONS:
//   refresh() -- pull /dashboard/summary, write summary, never throw
//   reset()   -- null out summary + error (logout / role switch)
//
// RACE POLICY.
//   Last write wins. Balances are a snapshot -- real protection
//   comes from call-site sequencing (`await refresh()` before
//   branching on values), not an epoch guard. If a concrete race
//   shows up, promote to the stores/products epoch pattern.
//
// TD-F08a NOTE.
//   BalanceResponse has no `currency` field -- the whole system
//   assumes USD cents. When multi-currency lands, the store grows
//   a `currency` ref and callers of formatPrice() drop the
//   `undefined` escape. Tracked centrally under TD-F08a.
// =============================================================================

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { getDashboardSummary } from '@/api/dashboard'
import type {
  BalanceResponse,
  DashboardSummaryResponse,
} from '@/api/types'

function emptyBalance(): BalanceResponse {
  return { confirmed: 0, frozen: 0 }
}

export const useDashboardStore = defineStore('dashboard', () => {
  const summary = ref<DashboardSummaryResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Convenience getters -- preserve the legacy F4.3 store surface
  // (activeBalance / passiveBalance) so the migration from
  // useBalanceStore does not rewrite every template. Return zeroed
  // placeholders before the first fetch resolves.
  const activeBalance = computed<BalanceResponse>(
    () => summary.value?.active_balance ?? emptyBalance(),
  )
  const passiveBalance = computed<BalanceResponse>(
    () => summary.value?.passive_balance ?? emptyBalance(),
  )

  /**
   * Pull /dashboard/summary and overwrite state.
   *
   * Never throws -- errors are captured on `error`. Callers that
   * need to branch on success should check `error` after
   * `await refresh()`.
   */
  async function refresh(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      summary.value = await getDashboardSummary()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
    } finally {
      loading.value = false
    }
  }

  /** Reset state. Called on logout and role switch. */
  function reset(): void {
    summary.value = null
    loading.value = false
    error.value = null
  }

  return {
    summary,
    loading,
    error,
    activeBalance,
    passiveBalance,
    refresh,
    reset,
  }
})
