// =============================================================================
// CBSHOME Frontend -- Staff Events API (iter 2.7 Block B)
// =============================================================================
//
// Typed wrappers for /api/v1/staff/events/* (backend
// posts/staff_router.py -- posts and events share one router module
// server-side, but the frontend keeps them in separate clients so
// each maps cleanly onto its own editor: PostListEditor vs EventEditor).
//
// All endpoints require the content_manage permission server-side;
// the frontend gates CTAs through useStaffPermissions().canDo(
// 'content_manage') before calling.
//
// Like staff posts, the staff event list returns drafts (and past
// events) that the public /api/v1/events surface hides. Soft-deleted
// rows stay hidden.
//
// Endpoints:
//   GET    /api/v1/staff/events          -- list (drafts + past + future)
//   POST   /api/v1/staff/events          -- create
//   PATCH  /api/v1/staff/events/{id}     -- partial update
//   DELETE /api/v1/staff/events/{id}     -- soft-delete
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type {
  EventListResponse,
  EventResponse,
  CreateEventRequest,
  UpdateEventRequest,
} from '@/api/types'

/**
 * GET /api/v1/staff/events -- paginated event list with optional filters.
 *
 * Filters (all optional, combinable):
 *   - is_published: true / false exact match; omit for both
 *   - upcoming:     true  -> only future events, starts_at ASC
 *                   false -> only past events, starts_at DESC
 *                   omit  -> both, starts_at DESC
 *   - search:       case-insensitive substring on title (backend
 *                   escapes %, _, \ so literals match)
 *
 * The `upcoming` split is evaluated against a single server-side
 * wall-clock value per request, so a slow request can't straddle the
 * now() boundary between count and page.
 *
 * Pagination: page (1-indexed), per_page (1..100).
 */
export function fetchStaffEvents(params?: {
  is_published?: boolean
  upcoming?: boolean
  search?: string
  page?: number
  per_page?: number
}): Promise<EventListResponse> {
  const qs = buildQueryString({
    is_published: params?.is_published,
    upcoming: params?.upcoming,
    search: params?.search,
    page: params?.page,
    per_page: params?.per_page,
  })
  return api.get<EventListResponse>(`/api/v1/staff/events${qs}`)
}

/** POST /api/v1/staff/events -- create a calendar event. */
export function createStaffEvent(body: CreateEventRequest): Promise<EventResponse> {
  return api.post<EventResponse>('/api/v1/staff/events', body)
}

/** PATCH /api/v1/staff/events/{id} -- partial update of an event. */
export function updateStaffEvent(
  eventId: string,
  body: UpdateEventRequest,
): Promise<EventResponse> {
  return api.patch<EventResponse>(`/api/v1/staff/events/${eventId}`, body)
}

/** DELETE /api/v1/staff/events/{id} -- soft-delete an event. */
export function deleteStaffEvent(eventId: string): Promise<void> {
  return api.delete(`/api/v1/staff/events/${eventId}`)
}
