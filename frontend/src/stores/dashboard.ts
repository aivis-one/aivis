// =============================================================================
// CBSHOME Frontend -- Dashboard Store (Phase F4.4 B2 + B5-post)
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
// RACE POLICY (B5-post).
//   Previously "last write wins". That left a window where rapid
//   tab switches (Dashboard <-> Balance, both call refresh() in
//   onMounted) could resolve out of order -- a slower earlier fetch
//   landing after a faster later one and displaying stale figures.
//   For a financial dashboard this is visually "jumping backwards"
//   numbers. Fixed with a monotonic epoch guard identical to the
//   pattern in stores/portfolio (two-epoch) and stores/transactions:
//     - refresh() captures its own epoch
//     - only the latest epoch may publish to summary / error / loading
//     - reset() bumps the epoch too, so a refresh() that resolves
//       after logout cannot repopulate summary behind the guard
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

  // Monotonic counter. Bumped by refresh() (on start) and reset()
  // (to invalidate any in-flight refresh). Non-reactive by design --
  // only read inside the async closure after await points.
  let epoch = 0

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
   *
   * Epoch-guarded: a second refresh() that starts before the first
   * resolves will supersede the first -- the loser's result is
   * dropped silently, and only the latest winner writes to summary /
   * error / loading.
   */
  async function refresh(): Promise<void> {
    const mine = ++epoch
    loading.value = true
    error.value = null
    try {
      const next = await getDashboardSummary()
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
   * back with the old user's data would otherwise overwrite the
   * cleared state.
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
    activeBalance,
    passiveBalance,
    refresh,
    reset,
  }
})
