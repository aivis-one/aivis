// =============================================================================
// AIVIS.ONE Frontend -- Agent Store (Task 2 Block A, Phase F6.1; Task 3 Block A)
// =============================================================================
//
// Pinia store backing AgentHubView (referral links + funnel stats),
// AgentDashboardView (rank / month commission / registrations widgets)
// and the Task 3 views (ReferralsView / CommissionsView /
// LeaderboardView reuse this same store + api/agent.ts layer -- do not
// duplicate it there).
//
// STATE GROUPS (each with its own loading / error pair + epoch):
//   links             -- paginated referral links, infinite-scroll shape
//                        (fetchFirstPage / loadMore / hasMore), same as
//                        stores/products.ts
//   stats             -- ReferralStatsResponse aggregate funnel
//   leaderboard       -- monthly snapshot; myRank computed from is_me
//   downline          -- two collections (investors L1-L3 + sub-agents);
//                        Task 3 ReferralsView consumer (Block B)
//   commissionSummary -- server-side month-to-date aggregate; backs the
//                        Dashboard "commission this month" widget
//   commissions       -- paginated commission history; Task 3
//                        CommissionsView consumer (Block C)
//
// WHAT IS DELIBERATELY NOT HERE:
//   balance -- AgentDashboardView reads passive_balance from the
//   existing stores/dashboard.ts (GET /dashboard/summary). One
//   endpoint, one store -- no duplication.
//
// RACE POLICY (FP-17, fixed in R45-2.1):
//   One monotonic epoch PER STATE GROUP (links / stats / leaderboard /
//   downline / commissionSummary / commissions), bumped by that
//   group's fetch and by reset(), and captured by the group's async
//   action. A resolve that lost the race writes nothing.
//
//   WHY PER-GROUP, NOT SHARED (R45-2.1 post-mortem): the first version
//   shared ONE counter across all groups, copying the single-fetch-path
//   stores (dashboard.ts / products.ts) without accounting for the
//   difference. Views fire several group fetches synchronously in
//   onMounted, so the shared counter reached its final value before any
//   response arrived -- every group except the last had its response
//   discarded AND its loading flag stuck true (the `finally` was
//   epoch-gated too). Deterministic infinite spinners on both agent
//   screens. Epochs only guard against STALE responses within the same
//   group; concurrent fetches of DIFFERENT groups are independent and
//   must never invalidate each other.
//
// MONTH-TO-DATE COMMISSION (Task 3 Block A):
//   commissionSummary holds the server-side month aggregate from
//   GET /agent/commissions/summary (current UTC month, frozen+confirmed,
//   reversed excluded). monthCommissionCents reads it directly. This
//   replaced the former client-side sum over the first 100 history
//   entries -- the server figure is exact, so the old
//   ">100-entries undercount / approximate" caveat is gone, and the
//   truncated flag that drove it has been removed
//   (TD-COMMISSION-MONTH-AGG closed).
//
// COMMIT / RESET:
//   reset() registered in stores/sessionReset.ts (logout + avatar
//   transitions). Never throws.
// =============================================================================

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  createReferralLink,
  getCommissionSummary,
  getDownline,
  getLeaderboard,
  getMyCommissions,
  getMyReferralLinks,
  getMyReferralStats,
} from '@/api/agent'
import type {
  CommissionEntry,
  CommissionSummaryResponse,
  LeaderboardResponse,
  ReferralDownlineResponse,
  ReferralLinkResponse,
  ReferralStatsResponse,
} from '@/api/types'

const LINKS_PER_PAGE = 20

// Page size for the paginated commission history (Task 3
// CommissionsView, Block C). The endpoint caps limit at 100.
const COMMISSIONS_PER_PAGE = 20

export const useAgentStore = defineStore('agent', () => {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  // -- Referral links (Hub list) --
  const links = ref<ReferralLinkResponse[]>([])
  const linksTotal = ref(0)
  const linksPage = ref(1)
  const linksLoading = ref(false)
  const linksError = ref<string | null>(null)

  // -- Aggregate funnel stats (Hub stats card + Dashboard widget) --
  const stats = ref<ReferralStatsResponse | null>(null)
  const statsLoading = ref(false)
  const statsError = ref<string | null>(null)

  // -- Leaderboard (Dashboard rank widget) --
  const leaderboard = ref<LeaderboardResponse | null>(null)
  const leaderboardLoading = ref(false)
  const leaderboardError = ref<string | null>(null)

  // -- Downline: investors (L1-L3) + sub-agents (Task 3 ReferralsView) --
  const downline = ref<ReferralDownlineResponse | null>(null)
  const downlineLoading = ref(false)
  const downlineError = ref<string | null>(null)

  // -- Month-to-date commission aggregate (Dashboard widget) --
  const commissionSummary = ref<CommissionSummaryResponse | null>(null)
  const commissionSummaryLoading = ref(false)
  const commissionSummaryError = ref<string | null>(null)

  // -- Commission history, paginated (Task 3 CommissionsView, Block C) --
  const commissions = ref<CommissionEntry[]>([])
  const commissionsTotal = ref(0)
  const commissionsLoading = ref(false)
  const commissionsError = ref<string | null>(null)

  // Monotonic per-group epochs (FP-17, R45-2.1). Non-reactive by
  // design -- read only inside async closures after await points. One
  // counter per independent state group: a fetch in one group must
  // never invalidate an in-flight fetch of another.
  let linksEpoch = 0
  let statsEpoch = 0
  let leaderboardEpoch = 0
  let downlineEpoch = 0
  let commissionSummaryEpoch = 0
  let commissionsEpoch = 0

  // ---------------------------------------------------------------------------
  // Computed
  // ---------------------------------------------------------------------------

  const hasMoreLinks = computed(
    () => links.value.length < linksTotal.value,
  )

  /**
   * Current agent's rank in the monthly leaderboard, or null when
   * outside the snapshot top or before the first snapshot exists.
   * The widget renders an em-dash for null -- honest "not ranked yet".
   */
  const myRank = computed<number | null>(() => {
    const me = leaderboard.value?.entries.find((e) => e.is_me)
    return me ? me.rank : null
  })

  /**
   * Month-to-date commission in cents, taken straight from the
   * server-side /agent/commissions/summary aggregate (current UTC
   * month, frozen+confirmed, reversed excluded). Exact -- replaces the
   * former client-side sum over the first 100 history entries; see
   * MONTH-TO-DATE COMMISSION in the header.
   */
  const monthCommissionCents = computed<number>(
    () => commissionSummary.value?.month_to_date_cents ?? 0,
  )

  /**
   * Whether more commission-history entries remain to load. Mirrors
   * hasMoreLinks: accumulated items < server total.
   */
  const hasMoreCommissions = computed(
    () => commissions.value.length < commissionsTotal.value,
  )

  // ---------------------------------------------------------------------------
  // Actions -- referral links (Hub)
  // ---------------------------------------------------------------------------

  /**
   * Load page 1 of the agent's links, replacing the list.
   * Never throws -- errors land on linksError.
   */
  async function fetchLinksFirstPage(): Promise<void> {
    const mine = ++linksEpoch
    linksLoading.value = true
    linksError.value = null
    try {
      const resp = await getMyReferralLinks(1, LINKS_PER_PAGE)
      if (mine !== linksEpoch) return
      links.value = resp.items
      linksTotal.value = resp.total
      linksPage.value = 1
    } catch (err) {
      if (mine !== linksEpoch) return
      linksError.value = err instanceof Error ? err.message : 'Unknown error'
    } finally {
      if (mine === linksEpoch) linksLoading.value = false
    }
  }

  /**
   * Append the next page. No-op while loading or when exhausted.
   * Never throws -- errors land on linksError.
   */
  async function loadMoreLinks(): Promise<void> {
    if (linksLoading.value || !hasMoreLinks.value) return
    const mine = ++linksEpoch
    linksLoading.value = true
    linksError.value = null
    try {
      const next = linksPage.value + 1
      const resp = await getMyReferralLinks(next, LINKS_PER_PAGE)
      if (mine !== linksEpoch) return
      links.value = [...links.value, ...resp.items]
      linksTotal.value = resp.total
      linksPage.value = next
    } catch (err) {
      if (mine !== linksEpoch) return
      linksError.value = err instanceof Error ? err.message : 'Unknown error'
    } finally {
      if (mine === linksEpoch) linksLoading.value = false
    }
  }

  /**
   * Create a new referral link and prepend it to the list -- no
   * refetch, no double request. Local mirrors keep the visible numbers
   * consistent: linksTotal and stats.total_links both +1.
   *
   * THROWS on failure (unlike the fetch actions): the Hub button is the
   * only caller and owns the error UX (toast). FP-04 double-submit
   * guard lives at the call-site via the returned promise + a local
   * `creating` flag in the view.
   */
  async function createLink(): Promise<ReferralLinkResponse> {
    const link = await createReferralLink()
    links.value = [link, ...links.value]
    linksTotal.value += 1
    if (stats.value) {
      stats.value = {
        ...stats.value,
        total_links: stats.value.total_links + 1,
      }
    }
    return link
  }

  // ---------------------------------------------------------------------------
  // Actions -- stats / leaderboard / downline / commission summary / history
  // ---------------------------------------------------------------------------

  /** Pull /referrals/stats/me. Never throws. */
  async function fetchStats(): Promise<void> {
    const mine = ++statsEpoch
    statsLoading.value = true
    statsError.value = null
    try {
      const resp = await getMyReferralStats()
      if (mine !== statsEpoch) return
      stats.value = resp
    } catch (err) {
      if (mine !== statsEpoch) return
      statsError.value = err instanceof Error ? err.message : 'Unknown error'
    } finally {
      if (mine === statsEpoch) statsLoading.value = false
    }
  }

  /** Pull /agent/leaderboard. Never throws. */
  async function fetchLeaderboard(): Promise<void> {
    const mine = ++leaderboardEpoch
    leaderboardLoading.value = true
    leaderboardError.value = null
    try {
      const resp = await getLeaderboard()
      if (mine !== leaderboardEpoch) return
      leaderboard.value = resp
    } catch (err) {
      if (mine !== leaderboardEpoch) return
      leaderboardError.value =
        err instanceof Error ? err.message : 'Unknown error'
    } finally {
      if (mine === leaderboardEpoch) leaderboardLoading.value = false
    }
  }

  /**
   * Pull /referrals/downline/me (investors L1-L3 + sub-agents).
   * Its own epoch (R45-2.1): a concurrent fetch of another group must
   * not invalidate this one. Never throws -- errors land on
   * downlineError.
   */
  async function fetchDownline(): Promise<void> {
    const mine = ++downlineEpoch
    downlineLoading.value = true
    downlineError.value = null
    try {
      const resp = await getDownline()
      if (mine !== downlineEpoch) return
      downline.value = resp
    } catch (err) {
      if (mine !== downlineEpoch) return
      downlineError.value =
        err instanceof Error ? err.message : 'Unknown error'
    } finally {
      if (mine === downlineEpoch) downlineLoading.value = false
    }
  }

  /** Pull /agent/commissions/summary (month-to-date). Never throws. */
  async function fetchCommissionSummary(): Promise<void> {
    const mine = ++commissionSummaryEpoch
    commissionSummaryLoading.value = true
    commissionSummaryError.value = null
    try {
      const resp = await getCommissionSummary()
      if (mine !== commissionSummaryEpoch) return
      commissionSummary.value = resp
    } catch (err) {
      if (mine !== commissionSummaryEpoch) return
      commissionSummaryError.value =
        err instanceof Error ? err.message : 'Unknown error'
    } finally {
      if (mine === commissionSummaryEpoch) {
        commissionSummaryLoading.value = false
      }
    }
  }

  /**
   * Load page 1 of commission history, REPLACING the list. Never
   * throws -- errors land on commissionsError. Shares commissionsEpoch
   * with loadMoreCommissions so a fresh first page invalidates any
   * in-flight append (R45-2.1).
   */
  async function fetchCommissionsFirstPage(): Promise<void> {
    const mine = ++commissionsEpoch
    commissionsLoading.value = true
    commissionsError.value = null
    try {
      const resp = await getMyCommissions(COMMISSIONS_PER_PAGE, 0)
      if (mine !== commissionsEpoch) return
      commissions.value = resp.items
      commissionsTotal.value = resp.total
    } catch (err) {
      if (mine !== commissionsEpoch) return
      commissionsError.value =
        err instanceof Error ? err.message : 'Unknown error'
    } finally {
      if (mine === commissionsEpoch) commissionsLoading.value = false
    }
  }

  /**
   * Append the next commission-history page. No-op while loading or
   * when exhausted. The endpoint is limit/offset, so offset = the
   * current item count. Never throws -- errors land on
   * commissionsError.
   */
  async function loadMoreCommissions(): Promise<void> {
    if (commissionsLoading.value || !hasMoreCommissions.value) return
    const mine = ++commissionsEpoch
    commissionsLoading.value = true
    commissionsError.value = null
    try {
      const resp = await getMyCommissions(
        COMMISSIONS_PER_PAGE,
        commissions.value.length,
      )
      if (mine !== commissionsEpoch) return
      commissions.value = [...commissions.value, ...resp.items]
      commissionsTotal.value = resp.total
    } catch (err) {
      if (mine !== commissionsEpoch) return
      commissionsError.value =
        err instanceof Error ? err.message : 'Unknown error'
    } finally {
      if (mine === commissionsEpoch) commissionsLoading.value = false
    }
  }

  // ---------------------------------------------------------------------------
  // Reset (sessionReset.ts contract)
  // ---------------------------------------------------------------------------

  /**
   * Drop all state. Bumps every group epoch first so in-flight fetches
   * resolving after logout cannot repopulate the cleared state -- ALL
   * SIX groups, not just one (the per-group split of R45-2.1 applies
   * here too). Synchronous, never throws.
   */
  function reset(): void {
    ++linksEpoch
    ++statsEpoch
    ++leaderboardEpoch
    ++downlineEpoch
    ++commissionSummaryEpoch
    ++commissionsEpoch
    links.value = []
    linksTotal.value = 0
    linksPage.value = 1
    linksLoading.value = false
    linksError.value = null
    stats.value = null
    statsLoading.value = false
    statsError.value = null
    leaderboard.value = null
    leaderboardLoading.value = false
    leaderboardError.value = null
    downline.value = null
    downlineLoading.value = false
    downlineError.value = null
    commissionSummary.value = null
    commissionSummaryLoading.value = false
    commissionSummaryError.value = null
    commissions.value = []
    commissionsTotal.value = 0
    commissionsLoading.value = false
    commissionsError.value = null
  }

  return {
    // links
    links,
    linksTotal,
    linksPage,
    linksLoading,
    linksError,
    hasMoreLinks,
    fetchLinksFirstPage,
    loadMoreLinks,
    createLink,
    // stats
    stats,
    statsLoading,
    statsError,
    fetchStats,
    // leaderboard
    leaderboard,
    leaderboardLoading,
    leaderboardError,
    myRank,
    fetchLeaderboard,
    // downline (Task 3 ReferralsView)
    downline,
    downlineLoading,
    downlineError,
    fetchDownline,
    // commission summary (month-to-date; Dashboard widget)
    commissionSummary,
    commissionSummaryLoading,
    commissionSummaryError,
    monthCommissionCents,
    fetchCommissionSummary,
    // commission history (Task 3 CommissionsView)
    commissions,
    commissionsTotal,
    commissionsLoading,
    commissionsError,
    hasMoreCommissions,
    fetchCommissionsFirstPage,
    loadMoreCommissions,
    // session
    reset,
  }
})
