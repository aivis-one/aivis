// =============================================================================
// AIVIS.ONE Frontend -- Dashboard API (Phase F4.2)
// =============================================================================
//
// Typed wrapper for /api/v1/dashboard/summary.
// Source of truth: backend/app/modules/dashboard/router.py (Sprint 9.2).
//
// F4.2 uses this endpoint as a one-shot balance probe on the
// Purchase / Installment confirm screens. F4.3 will promote the
// response into a Pinia balance store; keeping the call stateless
// here lets both phases share the same wrapper.
// =============================================================================

import { api } from '@/api/client'
import type { DashboardSummaryResponse } from '@/api/types'

/**
 * GET /api/v1/dashboard/summary
 *
 * Aggregated portfolio widget for the authenticated user. Users
 * without purchases get zeroed-out totals and an empty companies
 * list -- callers should not branch on role, they branch on values.
 */
export function getDashboardSummary(): Promise<DashboardSummaryResponse> {
  return api.get<DashboardSummaryResponse>('/api/v1/dashboard/summary')
}
