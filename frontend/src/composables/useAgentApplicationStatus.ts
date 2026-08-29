// =============================================================================
// AIVIS.ONE Frontend -- useAgentApplicationStatus Composable (TASK-39 item 5)
// =============================================================================
//
// Extracted from InvestorSettingsView's inline "Agent application" block so
// the state machine has exactly ONE implementation. InvestorSettingsView
// still owns the actual submit control (applyForAgent -> submitAgentApplication,
// api/agent-apps.ts); this composable only fetches /agent-applications/me and
// derives the same read-only state InvestorSettingsView used to compute
// locally. InvestorMoreView (the new "Agent programme" tile, more visible
// discoverability per the owner's item-5 ruling) calls this SAME composable
// rather than re-deriving the state machine, so the two screens cannot drift
// out of sync on what "pending" / "cooldown" / "can_apply" mean.
//
// Each caller gets its OWN instance (own refs, own fetch()) -- this is not a
// singleton store. Two screens mounted at once (e.g. dev tools split view)
// each do their own GET; that is the existing behaviour InvestorSettingsView
// already had (fetch on mount), just not duplicated as separate literal
// state-machine code.
//
// STATE MACHINE (unchanged from the original InvestorSettingsView header
// comment -- moved here verbatim):
//   loading       -- in flight
//   load_error    -- fetch failed. Caller should show an inline retry.
//   kyc_required  -- user.kyc_status != 'approved'.
//   pending       -- latest application status = pending.
//   cooldown      -- latest status = rejected AND cooldown_until is future.
//   can_reapply   -- latest status = rejected AND cooldown expired.
//   can_apply     -- no applications on record (also the defensive fallback
//                     for the unreachable "latest = approved" case: approval
//                     flips user.role to agent, which removes the investor
//                     from both InvestorShell and this composable's callers).
// =============================================================================

import { computed, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getMyAgentApplications } from '@/api/agent-apps'
import type { AgentApplicationResponse } from '@/api/types'

export type AgentApplicationState =
  | 'loading'
  | 'load_error'
  | 'kyc_required'
  | 'can_apply'
  | 'pending'
  | 'cooldown'
  | 'can_reapply'

export function useAgentApplicationStatus() {
  const authStore = useAuthStore()

  const isInvestor = computed<boolean>(() => authStore.role === 'investor')
  const kycApproved = computed<boolean>(() => authStore.kycStatus === 'approved')

  const apps = ref<AgentApplicationResponse[]>([])
  const loading = ref<boolean>(false)
  const loadErrored = ref<boolean>(false)

  // Newest-first per backend contract (get_my_applications orders by
  // created_at DESC), so items[0] is always "the latest".
  const latestApp = computed<AgentApplicationResponse | null>(() => apps.value[0] ?? null)

  const state = computed<AgentApplicationState>(() => {
    if (loading.value) return 'loading'
    if (loadErrored.value) return 'load_error'
    if (!kycApproved.value) return 'kyc_required'
    const last = latestApp.value
    if (!last) return 'can_apply'
    if (last.status === 'pending') return 'pending'
    if (last.status === 'rejected') {
      if (last.cooldown_until) {
        const until = new Date(last.cooldown_until).getTime()
        if (!Number.isNaN(until) && Date.now() < until) return 'cooldown'
      }
      return 'can_reapply'
    }
    return 'can_apply'
  })

  // Ceiling so a user at "22 hours remaining" sees "1 day left", never
  // "0 days left".
  const cooldownDaysLeft = computed<number>(() => {
    const last = latestApp.value
    if (!last?.cooldown_until) return 0
    const until = new Date(last.cooldown_until).getTime()
    if (Number.isNaN(until)) return 0
    const diff = until - Date.now()
    if (diff <= 0) return 0
    return Math.ceil(diff / (24 * 60 * 60 * 1000))
  })

  async function fetch(): Promise<void> {
    if (!isInvestor.value) return
    loading.value = true
    loadErrored.value = false
    try {
      const resp = await getMyAgentApplications()
      apps.value = resp.items
    } catch {
      loadErrored.value = true
    } finally {
      loading.value = false
    }
  }

  return {
    isInvestor,
    kycApproved,
    apps,
    loading,
    loadErrored,
    latestApp,
    state,
    cooldownDaysLeft,
    fetch,
  }
}
