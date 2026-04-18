// =============================================================================
// CBSHOME Frontend -- Balance Store (Phase F4.3)
// =============================================================================
//
// Pinia store exposing the authenticated user's ledger balances.
// Sourced from GET /api/v1/dashboard/summary (Sprint 9.2) -- the same
// endpoint F4.2 already uses inline on the purchase / installment
// confirm screens. Those call sites keep their inline probes for now
// and are scheduled to migrate onto this store in F4.4 (Dashboard /
// Portfolio), so the contract stays deliberately simple.
//
// STATE (all amounts in USD cents):
//   active_confirmed  -- spendable active balance
//   active_frozen     -- still-frozen active balance (not spendable)
//   passive_confirmed -- earnings ready to withdraw
//   passive_frozen    -- earnings still in cool-off
//   loading           -- true during refresh()
//   error             -- last refresh error message, null on success
//
// ACTIONS:
//   refresh()         -- pull /dashboard/summary, write state, never throw
//   reset()           -- zero out state (logout / role switch)
//
// RACE POLICY:
//   Last write wins. Balances are a snapshot -- a refresh fired after
//   a purchase should not be clobbered by a slower-in-flight earlier
//   request, but the real protection against that is call-site
//   sequencing (await refresh() before showing), not an epoch guard
//   here. If a concrete race bites, promote to the products-store
//   epoch pattern.
//
// TD-F08a NOTE:
//   BalanceResponse has no `currency` field -- the whole system
//   assumes USD cents. When multi-currency lands, the store grows a
//   `currency` ref and callers of formatPrice() drop the `undefined`
//   escape. Tracked centrally under TD-F08a.
// =============================================================================

import { ref } from 'vue'
import { defineStore } from 'pinia'

import { getDashboardSummary } from '@/api/dashboard'

export const useBalanceStore = defineStore('balance', () => {
  const active_confirmed = ref(0)
  const active_frozen = ref(0)
  const passive_confirmed = ref(0)
  const passive_frozen = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * Pull ledger balances from /dashboard/summary and overwrite state.
   *
   * Never throws -- errors are captured on `error`. Callers that need
   * to branch on success should check `error` after `await refresh()`.
   */
  async function refresh(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const summary = await getDashboardSummary()
      active_confirmed.value = summary.active_balance.confirmed
      active_frozen.value = summary.active_balance.frozen
      passive_confirmed.value = summary.passive_balance.confirmed
      passive_frozen.value = summary.passive_balance.frozen
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
    } finally {
      loading.value = false
    }
  }

  /** Reset all balances to zero. Called on logout and role switch. */
  function reset(): void {
    active_confirmed.value = 0
    active_frozen.value = 0
    passive_confirmed.value = 0
    passive_frozen.value = 0
    loading.value = false
    error.value = null
  }

  return {
    active_confirmed,
    active_frozen,
    passive_confirmed,
    passive_frozen,
    loading,
    error,
    refresh,
    reset,
  }
})
