// =============================================================================
// CBSHOME Frontend -- Company Profile Store (Phase F5.1)
// =============================================================================
//
// Pinia store exposing the authenticated company's full profile
// (CompanyResponse) to every company-side view that needs the
// company's identity, branding, or `id` (for filtering products by
// `company_id`). Source of truth for the staff-side schema, served
// by GET /api/v1/companies/me (Sprint 4.5).
//
// CALL SITES.
//   F5.1 CompanyDashboardView -- hero (logo + name) + companion
//                                fetch alongside the dashboard refresh.
//   F5.2 CompanyProductsView  -- needs `id` to filter products list.
//   F5.2 CompanySettingsView  -- read-only render of the full profile
//                                (distribution_config, payout, etc).
//
// STATE (snake_case server-side, kept as-is on the wire).
//   profile  -- CompanyResponse | null. Null until first successful load.
//   loading  -- true while loadIfMissing()'s fetch is in flight.
//   error    -- last load error message, null on success or pre-load.
//
// LOAD SEMANTICS -- CACHE-FIRST.
//   loadIfMissing() returns immediately if `profile` is already set.
//   The profile is owned by staff (no inline edits from F5.x), so a
//   successful load stays valid for the session. Multiple call sites
//   (Dashboard onMounted, Products onMounted, Settings onMounted) can
//   all call loadIfMissing() without a coordinator; the second and
//   later calls are no-ops once the first has resolved successfully.
//
//   When the profile *does* need to be invalidated -- on logout,
//   role switch, or (future) inline-edit completion -- callers use
//   reset() which clears state AND bumps the epoch so any in-flight
//   loadIfMissing() that resolves afterwards cannot repopulate the
//   stale values.
//
// FAILURE RECOVERY.
//   On error, `profile` stays null and `error` holds the message.
//   The next loadIfMissing() call retries (cache-miss path). Views
//   showing a Retry button just call loadIfMissing() again -- there
//   is no separate retry() action, the cache check is the gate.
//
// EPOCH GUARD (FP-17).
//   Standard pattern from stores/dashboard.ts. Plain `let` is
//   correct here: Pinia instantiates the store once per app, so the
//   closure lives for the entire app lifetime. Only the latest
//   epoch's resolve may publish to profile / error / loading.
// =============================================================================

import { ref } from 'vue'
import { defineStore } from 'pinia'

import { getMyCompany } from '@/api/companies'
import type { CompanyResponse } from '@/api/types'

export const useCompanyProfileStore = defineStore('companyProfile', () => {
  const profile = ref<CompanyResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Monotonic counter. Bumped by loadIfMissing() (on cache-miss
  // start) and reset() (to invalidate any in-flight load).
  // Non-reactive by design -- only read inside async closures
  // after await points.
  let epoch = 0

  /**
   * Load the company profile if it has not been loaded yet.
   *
   * Cache hit: returns immediately, no network call.
   * Cache miss: fetches GET /api/v1/companies/me, populates
   * `profile` on success or sets `error` on failure.
   *
   * Never throws -- views check `error` after `await` if they need
   * to branch on success.
   *
   * Epoch-guarded: a reset() during the fetch causes the resolve to
   * be silently dropped, so a post-logout response cannot rewrite
   * the cleared state.
   */
  async function loadIfMissing(): Promise<void> {
    // Cache hit -- reset() must be used to force a refetch.
    if (profile.value !== null) return

    const mine = ++epoch
    loading.value = true
    error.value = null
    try {
      const next = await getMyCompany()
      if (mine !== epoch) return
      profile.value = next
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
   * Clear cached state. Called on logout / role switch.
   *
   * Bumps the epoch so any in-flight loadIfMissing() that resolves
   * AFTER reset() cannot repopulate the profile -- a post-logout
   * fetch coming back with the previous user's company would
   * otherwise overwrite the cleared state.
   */
  function reset(): void {
    epoch += 1
    profile.value = null
    loading.value = false
    error.value = null
  }

  return {
    profile,
    loading,
    error,
    loadIfMissing,
    reset,
  }
})
