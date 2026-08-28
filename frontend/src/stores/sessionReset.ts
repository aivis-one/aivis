// =============================================================================
// AIVIS.ONE Frontend -- Session Reset Helper (Phase F5.1 B1)
// =============================================================================
//
// Centralised "drop every data store" call used by:
//   - stores/auth.ts._clearSession()       on logout / 401
//   - composables/useAvatar.ts             on avatar mode start AND end,
//                                          before each fetchMe()
//
// WHY A HELPER.
//   Four call sites need to call .reset() on every data store
//   (_clearSession + 2x avatar happy-paths + 2x avatar catch-paths).
//   Inlining the seven calls in four places is exactly the maintenance
//   pattern that produced the "nobody ever wired reset() into
//   _clearSession" bug this commit is fixing -- a future eighth store
//   would have to be threaded through four files in lockstep, and
//   inevitably one would be missed.
//
// CIRCULAR IMPORT NOTE.
//   None of the stores listed below imports useAuthStore or any other
//   store, so importing them all from this helper is safe. The helper
//   itself MUST NOT import useAuthStore -- auth.ts imports this helper,
//   and going the other way would create a cycle.
//
// PINIA INVOCATION SAFETY.
//   useXxxStore() is a runtime call here, invoked only inside the
//   exported function. By the time _clearSession() or useAvatar's
//   transitions fire, the app is fully bootstrapped and Pinia is
//   active -- the stores are guaranteed to instantiate.
//
// SCOPE.
//   "Data stores" = every Pinia store that holds user-scoped or
//   user-driven state. Explicitly NOT included:
//     - stores/auth.ts -- the caller owns the session itself; clearing
//                         token / user / loading is the caller's job.
// =============================================================================

import { useAgentStore } from '@/stores/agent'
import { useAttachmentsStore } from '@/stores/attachments'
import { useCompanyDashboardStore } from '@/stores/companyDashboard'
import { useCompanyListStore } from '@/stores/companyList'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import { useDashboardStore } from '@/stores/dashboard'
import { useNotificationsStore } from '@/stores/notifications'
import { usePortfolioStore } from '@/stores/portfolio'
import { useProductsStore } from '@/stores/products'
import { useSupportStore } from '@/stores/support'
import { useTransactionsStore } from '@/stores/transactions'

/**
 * Reset every data-bearing Pinia store to its initial state.
 *
 * Each store's reset() bumps its FP-17 epoch counter first, so any
 * in-flight fetch that resolves AFTER this call cannot repopulate the
 * cleared state. See AIVIS-Frontend.md § FP-17.
 *
 * Synchronous and never throws -- each reset() is a pure ref-mutation
 * sequence by contract.
 *
 * iter 2.5 batch 4: +useCompanyListStore (Investor companies tab) and
 * +useAttachmentsStore (CompanyOverview documents section, R2 §7.1).
 *
 * iter 2.5 batch 8: -useCompaniesStore. The legacy store backed the
 * deleted CompanyFilterSheet on MarketView; both are gone now that
 * the catalogue moved to CompanyListView and per-company products
 * live in ProductsByCompanyView (R1 §1.4). One fewer reset call.
 *
 * Task 2 Block A (F6.1): +useAgentStore (AgentHubView referral links
 * and stats, AgentDashboardView rank/commission widgets). Without
 * this line the agent's links and earnings would survive logout.
 *
 * Ф-1: +useSupportStore (user's own request thread, operator queue).
 * A staff member's queue and claim state, or a user's own thread,
 * left unreset would survive into the next session behind the same
 * tab -- exactly the class of bug this file exists to close, one line
 * to add rather than a store quietly missing from the list.
 *
 * Phase 6: +useNotificationsStore (the bell's badge + inbox feed).
 * Its reset() also stops the poll timer -- see that store's header --
 * so this is the one call site a next signed-in user's badge depends
 * on not being skipped.
 */
export function resetAllDataStores(): void {
  useDashboardStore().reset()
  usePortfolioStore().reset()
  useTransactionsStore().reset()
  useProductsStore().reset()
  useCompanyListStore().reset()
  useAttachmentsStore().reset()
  useCompanyProfileStore().reset()
  useCompanyDashboardStore().reset()
  useAgentStore().reset()
  useSupportStore().reset()
  useNotificationsStore().reset()
}
