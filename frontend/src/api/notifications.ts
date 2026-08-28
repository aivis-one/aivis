// =============================================================================
// AIVIS.ONE Frontend -- Notifications inbox API (Phase 6, the bell)
// =============================================================================
//
// Typed wrappers for /api/v1/notifications/*. Source of truth:
// backend/app/modules/notifications/router.py + schemas.py -- unlike
// api/support.ts, the backend here returns REAL typed responses
// (InboxPageOut, UnreadCountOut), so this file reads those straight
// out of api/generated.ts instead of hand-declaring shapes read off a
// forwarded comms payload.
//
// There is no request body anywhere on this surface and no
// recipient/user id parameter to accept: every call is scoped to the
// caller's own session on the backend (get_current_user), matching
// the trust-model requirement documented in
// notifications/service.py's header.
// =============================================================================

import { api } from '@/api/client'
import { buildQueryString } from '@/utils/querystring'
import type { InboxPageOut, UnreadCountOut } from '@/api/generated'

export interface ListInboxParams {
  limit?: number
  cursor?: string
}

/**
 * GET /api/v1/notifications -- the caller's own inbox, newest first,
 * plus the unread badge in the same round trip.
 *
 * On a box with no comms configured, or once comms is unreachable,
 * see notifications/service.py's header: the former degrades to an
 * honestly empty page (200), the latter surfaces as a real
 * ApiResponseError (502/504) from api/client.ts.
 */
export function listNotifications(params?: ListInboxParams): Promise<InboxPageOut> {
  const qs = buildQueryString({
    limit: params?.limit,
    cursor: params?.cursor,
  })
  return api.get<InboxPageOut>(`/api/v1/notifications${qs}`)
}

/**
 * GET /api/v1/notifications/unread-count -- the badge alone, for
 * cheap polling without paying for the feed.
 */
export function getUnreadNotificationCount(): Promise<UnreadCountOut> {
  return api.get<UnreadCountOut>('/api/v1/notifications/unread-count')
}

/**
 * POST /api/v1/notifications/{id}/read -- mark one delivery read
 * (idempotent); returns the fresh badge. 404 if the id names no
 * delivery of the caller's.
 */
export function markNotificationRead(deliveryId: string): Promise<UnreadCountOut> {
  return api.post<UnreadCountOut>(`/api/v1/notifications/${deliveryId}/read`)
}

/**
 * POST /api/v1/notifications/read-all -- mark every unread delivery
 * read; returns the fresh badge (always `{ unread: 0 }` on success).
 */
export function markAllNotificationsRead(): Promise<UnreadCountOut> {
  return api.post<UnreadCountOut>('/api/v1/notifications/read-all')
}
