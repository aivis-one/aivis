// =============================================================================
// CBSHOME Frontend -- Session Reset Helper (Phase F5.1 B1)
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

import { useCompaniesStore } from '@/stores/companies'
import { useCompanyDashboardStore } from '@/stores/companyDashboard'
import { useCompanyProfileStore } from '@/stores/companyProfile'
import { useDashboardStore } from '@/stores/dashboard'
import { usePortfolioStore } from '@/stores/portfolio'
import { useProductsStore } from '@/stores/products'
import { useTransactionsStore } from '@/stores/transactions'

/**
 * Reset every data-bearing Pinia store to its initial state.
 *
 * Each store's reset() bumps its FP-17 epoch counter first, so any
 * in-flight fetch that resolves AFTER this call cannot repopulate the
 * cleared state. See CBSHOME-Frontend.md § FP-17.
 *
 * Synchronous and never throws -- each reset() is a pure ref-mutation
 * sequence by contract.
 */
export function resetAllDataStores(): void {
  useDashboardStore().reset()
  usePortfolioStore().reset()
  useTransactionsStore().reset()
  useProductsStore().reset()
  useCompaniesStore().reset()
  useCompanyProfileStore().reset()
  useCompanyDashboardStore().reset()
}
