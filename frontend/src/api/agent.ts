// =============================================================================
// AIVIS.ONE Frontend -- Agent API (Task 2 Block A, Phase F6.1)
// =============================================================================
//
// Typed wrappers for the agent-side endpoints consumed by
// AgentHubView / AgentDashboardView (and, in Task 3, the full
// CommissionsView / LeaderboardView -- reuse this module there, do
// not duplicate the layer).
//
// Source of truth:
//   backend/app/modules/referrals/router.py   (Sprint 7.2 + Task 1 D)
//   backend/app/modules/commissions/router.py (Sprint 7.3)
//
// All wrappers are stateless one-liners over `api` (same shape as
// api/dashboard.ts). State lives in stores/agent.ts.
// =============================================================================

import { api } from '@/api/client'
import type {
  CommissionListResponse,
  CommissionSummaryResponse,
  LeaderboardResponse,
  ReferralDownlineResponse,
  ReferralLinkListResponse,
  ReferralLinkResponse,
  ReferralStatsResponse,
} from '@/api/types'

/**
 * POST /api/v1/referrals/links
 *
 * Create a new referral link for the authenticated agent. The 201
 * response carries the full per-link contract with zeroed counters
 * (a brand-new link has no clicks / registrations / purchases).
 */
export function createReferralLink(): Promise<ReferralLinkResponse> {
  return api.post<ReferralLinkResponse>('/api/v1/referrals/links')
}

/**
 * GET /api/v1/referrals/links/me
 *
 * Paginated list of the agent's links, each enriched with
 * click_count / registration_count / purchase_count + is_active
 * (backend Task 1 Block D -- two batched aggregates, no N+1).
 */
export function getMyReferralLinks(page = 1, perPage = 20): Promise<ReferralLinkListResponse> {
  return api.get<ReferralLinkListResponse>(
    `/api/v1/referrals/links/me?page=${page}&per_page=${perPage}`,
  )
}

/**
 * GET /api/v1/referrals/stats/me
 *
 * Aggregate funnel for the agent: total_links -> total_clicks ->
 * total_registrations -> total_purchases -> total_commission_cents.
 */
export function getMyReferralStats(): Promise<ReferralStatsResponse> {
  return api.get<ReferralStatsResponse>('/api/v1/referrals/stats/me')
}

/**
 * GET /api/v1/referrals/downline/me
 *
 * The agent's downline as two collections (decision #1 -- not a
 * polymorphic flat tree): investors at commission-mirror levels L1-L3
 * and sub-agents at agent-hop depth 1-3. display_name is masked
 * server-side; the server sorts investors by level then registered_at.
 * No pagination (decision #7 -- depth-3 bounds the size). Agent only
 * (403 otherwise).
 */
export function getDownline(): Promise<ReferralDownlineResponse> {
  return api.get<ReferralDownlineResponse>('/api/v1/referrals/downline/me')
}

/**
 * GET /api/v1/agent/leaderboard
 *
 * Current monthly leaderboard snapshot (top agents). The caller's
 * own row is flagged with is_me; entries is empty until the
 * leaderboard worker has produced the first snapshot of the period.
 */
export function getLeaderboard(): Promise<LeaderboardResponse> {
  return api.get<LeaderboardResponse>('/api/v1/agent/leaderboard')
}

/**
 * GET /api/v1/agent/commissions/me
 *
 * Commission + volume-bonus history, newest first.
 * limit is capped at 100 server-side.
 */
export function getMyCommissions(limit = 50, offset = 0): Promise<CommissionListResponse> {
  return api.get<CommissionListResponse>(
    `/api/v1/agent/commissions/me?limit=${limit}&offset=${offset}`,
  )
}

/**
 * GET /api/v1/agent/commissions/summary
 *
 * Month-to-date commission aggregate for the current UTC month
 * (frozen+confirmed, reversed excluded). Server-side replacement for
 * the dashboard's former client-side sum over the first 100 history
 * entries (TD-COMMISSION-MONTH-AGG). Agent only.
 */
export function getCommissionSummary(): Promise<CommissionSummaryResponse> {
  return api.get<CommissionSummaryResponse>('/api/v1/agent/commissions/summary')
}
