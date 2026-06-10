// =============================================================================
// CBSHOME Frontend -- Agent Store (Task 2 Block A, Phase F6.1)
// =============================================================================
//
// Pinia store backing AgentHubView (referral links + funnel stats)
// and AgentDashboardView (rank / month commission / registrations
// widgets). Task 3 views (CommissionsView / LeaderboardView) reuse
// the same store + api/agent.ts layer -- do not duplicate it there.
//
// STATE GROUPS (each with its own loading / error pair):
//   links        -- paginated referral links, infinite-scroll shape
//                   (fetchFirstPage / loadMore / hasMore), same as
//                   stores/products.ts
//   stats        -- ReferralStatsResponse aggregate funnel
//   leaderboard  -- monthly snapshot; myRank computed from is_me
//   commissions  -- first page of commission history;
//                   monthCommissionCents computed client-side
//
// WHAT IS DELIBERATELY NOT HERE:
//   balance -- AgentDashboardView reads passive_balance from the
//   existing stores/dashboard.ts (GET /dashboard/summary). One
//   endpoint, one store -- no duplication.
//
// RACE POLICY (FP-17, fixed in R45-2.1):
//   One monotonic epoch PER STATE GROUP (links / stats / leaderboard /
//   commissions), bumped by that group's fetch and by reset(), and
//   captured by the group's async action. A resolve that lost the
//   race writes nothing.
//
//   WHY PER-GROUP, NOT SHARED (R45-2.1 post-mortem): the first
//   version shared ONE counter across all four groups, copying the
//   single-fetch-path stores (dashboard.ts / products.ts) without
//   accounting for the difference. Views fire several group fetches
//   synchronously in onMounted, so the shared counter reached its
//   final value before any response arrived -- every group except the
//   last had its response discarded AND its loading flag stuck true
//   (the `finally` was epoch-gated too). Deterministic infinite
//   spinners on both agent screens. Epochs only guard against STALE
//   responses within the same group; concurrent fetches of DIFFERENT
//   groups are independent and must never invalidate each other.
//
// MONTH COMMISSION CAVEAT:
//   There is no server-side "commission this month" aggregate yet.
//   monthCommissionCents sums the first MONTH_FETCH_LIMIT (100)
//   history entries that fall in the current UTC month -- both
//   frozen and confirmed count as "earned". An agent with >100
//   entries in one month would be undercounted; flagged in the Task 2
//   report as a backend candidate for Task 2b/3.
//
// COMMIT / RESET:
//   reset() registered in stores/sessionReset.ts (logout + avatar
//   transitions). Never throws.
// =============================================================================

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  createReferralLink,
  getLeaderboard,
  getMyCommissions,
  getMyReferralLinks,
  getMyReferralStats,
} from '@/api/agent'
import type {
  CommissionListResponse,
  LeaderboardResponse,
  ReferralLinkResponse,
  ReferralStatsResponse,
} from '@/api/types'

const LINKS_PER_PAGE = 20

// limit=100 is the server-side cap for /agent/commissions/me; one
// page is the best month approximation available today (see header).
const MONTH_FETCH_LIMIT = 100

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

  // -- Commission history (Dashboard month-commission widget) --
  const commissions = ref<CommissionListResponse | null>(null)
  const commissionsLoading = ref(false)
  const commissionsError = ref<string | null>(null)

  // Monotonic per-group epochs (FP-17, R45-2.1). Non-reactive by
  // design -- read only inside async closures after await points.
  // One counter per independent state group: a fetch in one group
  // must never invalidate an in-flight fetch of another.
  let linksEpoch = 0
  let statsEpoch = 0
  let leaderboardEpoch = 0
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
   * Commission accrued in the current UTC month, in cents. Sums both
   * frozen and confirmed entries (both are earned; frozen is merely
   * not yet withdrawable). See MONTH COMMISSION CAVEAT in the header.
   */
  const monthCommissionCents = computed<number>(() => {
    const items = commissions.value?.items
    if (!items) return 0
    const now = new Date()
    const monthStart = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)
    return items.reduce((sum, item) => {
      const ts = Date.parse(item.created_at)
      return ts >= monthStart ? sum + item.amount_cents : sum
    }, 0)
  })

  /**
   * True when the commission history page came back full
   * (items.length >= MONTH_FETCH_LIMIT) -- the month sum may then be
   * undercounted and the widget must say so (R45-2.2). Disappears
   * once a server-side monthly aggregate exists (Task 2b/3 candidate).
   */
  const monthCommissionTruncated = computed<boolean>(
    () => (commissions.value?.items.length ?? 0) >= MONTH_FETCH_LIMIT,
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
   * refetch, no double request. Local mirrors keep the visible
   * numbers consistent: linksTotal and stats.total_links both +1.
   *
   * THROWS on failure (unlike the fetch actions): the Hub button is
   * the only caller and owns the error UX (toast). FP-04 double-submit
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
  // Actions -- aggregate stats / leaderboard / commissions
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

  /** Pull the first commission-history page. Never throws. */
  async function fetchCommissions(): Promise<void> {
    const mine = ++commissionsEpoch
    commissionsLoading.value = true
    commissionsError.value = null
    try {
      const resp = await getMyCommissions(MONTH_FETCH_LIMIT, 0)
      if (mine !== commissionsEpoch) return
      commissions.value = resp
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
   * Drop all state. Bumps every group epoch first so in-flight
   * fetches resolving after logout cannot repopulate the cleared
   * state -- ALL FOUR groups, not just one (the per-group split of
   * R45-2.1 applies here too). Synchronous, never throws.
   */
  function reset(): void {
    ++linksEpoch
    ++statsEpoch
    ++leaderboardEpoch
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
    commissions.value = null
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
    // commissions
    commissions,
    commissionsLoading,
    commissionsError,
    monthCommissionCents,
    monthCommissionTruncated,
    fetchCommissions,
    // session
    reset,
  }
})
