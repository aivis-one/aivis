// =============================================================================
// AIVIS.ONE Frontend -- Agent Applications API (Phase F4.4, investor side)
// =============================================================================
//
// Typed wrappers for the investor-facing agent application endpoints.
// Source of truth: backend/app/modules/agent_applications/router.py
// (Sprint 7.1).
//
// ENDPOINTS WRAPPED:
//   POST /api/v1/agent-applications      -- submit a new application (201)
//   GET  /api/v1/agent-applications/me   -- history for the caller (200)
//
// STAFF-SIDE NOTE.
//   Staff endpoints (queue / approve / reject) live under
//   /api/v1/staff/agent-applications and are wrapped elsewhere
//   (api/admin.ts). This module is investor-only -- no staff
//   helpers leak in.
//
// PAGINATION DECISION.
//   Backend supports ?page&per_page on /me, but practically every
//   investor has 1-3 applications in their lifetime (the flow is:
//   submit -> pending -> approved terminal, or rejected -> 30-day
//   cooldown -> resubmit). Wrapping it into a paged API on the
//   frontend adds ceremony nobody needs. getMyAgentApplications()
//   omits the params entirely; backend defaults of page=1 /
//   per_page=20 return the full history for any realistic user.
//   If F6.x ever needs paging, extend here -- do not preempt.
//
// RATE LIMIT / CONFLICT SHAPES.
//   POST can respond 400 (not an investor / cooldown active) or
//   409 (pending application already exists). Callers narrow via
//   instanceof ApiResponseError + status; message text is a
//   human-readable fallback until backend emits error_code
//   (TD-F08c still open).
// =============================================================================

import { api } from '@/api/client'
import type {
  AgentApplicationListResponse,
  AgentApplicationResponse,
} from '@/api/types'

/**
 * POST /api/v1/agent-applications
 *
 * Submit a new agent application. Only callable by investors.
 * Returns 201 + the created record on success. Throws
 * ApiResponseError on the usual rejection cases (see module
 * header for the status taxonomy).
 */
export function submitAgentApplication(): Promise<AgentApplicationResponse> {
  return api.post<AgentApplicationResponse>('/api/v1/agent-applications')
}

/**
 * GET /api/v1/agent-applications/me
 *
 * List the caller's full application history, newest first. Shape
 * is `{ items, total }` -- no page / per_page echoed back (backend
 * schema omits them for this endpoint).
 */
export function getMyAgentApplications(): Promise<AgentApplicationListResponse> {
  return api.get<AgentApplicationListResponse>(
    '/api/v1/agent-applications/me',
  )
}
