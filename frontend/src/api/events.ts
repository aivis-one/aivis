// =============================================================================
// CBSHOME Frontend -- Events API (iter 2.7b, public surface)
// =============================================================================
//
// Typed wrappers for the public events surface.
// Source of truth: backend/app/modules/posts/router.py events_router
// (posts and events share one router module server-side; the frontend
// keeps a separate client per surface, matching staff-events.ts).
//
// ENDPOINTS WRAPPED (iter 2.7b):
//   GET  /api/v1/events?upcoming=<bool>   -- paginated list (Block C)
//   GET  /api/v1/events/upcoming?limit=N  -- next N, soonest first (Block B)
//
// SCOPE NOTE.
//   listUpcomingEvents (the /upcoming probe) feeds the dashboard
//   widget; listPublicEvents (paginated /events) feeds the full
//   /investor/events screen. Two endpoints, two response shapes, so
//   neither wrapper returns a shape-shifting union.
//
// AUTH.
//   Backend uses get_optional_user -- anonymous callers get the same
//   list. The wrapper does not branch on auth state; the API client
//   attaches the Bearer token when present.
//
// RESPONSE SHAPE.
//   /upcoming returns a bare list[EventResponse] (no pagination
//   envelope) -- the widget renders the top N and never paginates.
//   This is deliberately a different endpoint from the paginated
//   /events (Block C) so neither response is a shape-shifting union.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type { EventListResponse, EventResponse } from '@/api/types'

/**
 * GET /api/v1/events -- paginated published events.
 *
 * iter 2.7b A added the optional `upcoming` split:
 *   upcoming=true  -> future events, soonest first (ASC).
 *   upcoming=false -> past events, most recent first (DESC).
 *   omitted        -> all published, DESC (pre-2.7b behaviour).
 *
 * Drives the full /investor/events screen (Block C), which paginates
 * with infinite scroll. Always returns the EventListResponse envelope
 * ({ items, total, page, per_page }) -- distinct from /upcoming, which
 * returns a bare list, so neither response is a shape-shifting union.
 */
export function listPublicEvents(params?: {
  upcoming?: boolean
  page?: number
  per_page?: number
}): Promise<EventListResponse> {
  const qs = buildQueryString({
    upcoming: params?.upcoming,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<EventListResponse>(`/api/v1/events${qs}`)
}

/**
 * GET /api/v1/events/upcoming
 *
 * The next `limit` published events with starts_at >= now(), ordered
 * soonest first. Returns a plain array (no pagination wrapper). The
 * backend clamps `limit` to a ceiling (settings.events_upcoming_max_limit,
 * 50) and defaults to 3 when omitted; the dashboard widget passes 3.
 */
export function listUpcomingEvents(
  limit?: number,
): Promise<EventResponse[]> {
  const qs = buildQueryString({ limit })
  return api.get<EventResponse[]>(`/api/v1/events/upcoming${qs}`)
}
