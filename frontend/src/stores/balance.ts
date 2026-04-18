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
//   activeBalance  -- { confirmed, frozen } -- spendable + locked active
//   passiveBalance -- { confirmed, frozen } -- withdrawable + cool-off
//                                              earnings
//   loading        -- true during refresh()
//   error          -- last refresh error message, null on success
//
// Mirrors the backend BalanceResponse shape ({ confirmed, frozen })
// rather than flattening to four top-level refs. CamelCase keys match
// the rest of the stores (products, companies, auth).
//
// ACTIONS:
//   refresh() -- pull /dashboard/summary, write state, never throw
//   reset()   -- zero out state (logout / role switch)
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
import type { BalanceResponse } from '@/api/types'

function emptyBalance(): BalanceResponse {
  return { confirmed: 0, frozen: 0 }
}

export const useBalanceStore = defineStore('balance', () => {
  const activeBalance = ref<BalanceResponse>(emptyBalance())
  const passiveBalance = ref<BalanceResponse>(emptyBalance())
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * Pull ledger balances from /dashboard/summary and overwrite state.
   *
   * Never throws -- errors are captured on `error`. Callers that need
   * to branch on success should check `error` after `await refresh()`.
   *
   * Assigns fresh objects rather than spreading the response, so an
   * unexpected future field on BalanceResponse can't leak into the
   * store silently.
   */
  async function refresh(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const summary = await getDashboardSummary()
      activeBalance.value = {
        confirmed: summary.active_balance.confirmed,
        frozen: summary.active_balance.frozen,
      }
      passiveBalance.value = {
        confirmed: summary.passive_balance.confirmed,
        frozen: summary.passive_balance.frozen,
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
    } finally {
      loading.value = false
    }
  }

  /** Reset all balances to zero. Called on logout and role switch. */
  function reset(): void {
    activeBalance.value = emptyBalance()
    passiveBalance.value = emptyBalance()
    loading.value = false
    error.value = null
  }

  return {
    activeBalance,
    passiveBalance,
    loading,
    error,
    refresh,
    reset,
  }
})
