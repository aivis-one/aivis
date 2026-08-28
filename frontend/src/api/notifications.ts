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
import type { InboxPageOut, PreferencesOut, PreferencesPatchIn, UnreadCountOut } from '@/api/generated'

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

// =============================================================================
// Preferences (TASK-38 item 4) -- the settings screen
// =============================================================================
//
// generated.ts types `categories` as `Record<string, unknown>` on both
// PreferencesOut and PreferencesPatchIn: scripts/generate_ts_types.py
// collapses every `dict[str, X]` to `Record<string, unknown>` regardless
// of X (see e.g. `permissions`, `users_by_role` elsewhere in
// generated.ts -- this is an existing, repo-wide generator limitation,
// not something specific to this endpoint). CategoryToggles below is
// this call site's own narrower view (every value IS a boolean on the
// real wire, per notifications/schemas.py's PreferencesOut/PatchIn) --
// it does not change what is sent or received, only what the component
// is allowed to assume once it has the response in hand.
export interface CategoryToggles {
  [category: string]: boolean
}

/** The quiet-hours window, comms' wire shape (HH:MM local time strings, mon..sun day codes). */
export interface NotificationSchedule {
  from: string
  to: string
  days: string[]
}

export interface NotificationPreferences {
  categories: CategoryToggles
  schedule: NotificationSchedule | null
  /** READ-ONLY context -- see notifications/schemas.py's ScheduleOut/PreferencesOut. */
  timezone: string | null
}

export interface NotificationPreferencesPatch {
  /** Partial: only the listed keys change. Omit entirely to leave every category as-is. */
  categories?: CategoryToggles
  /** Full replace when present; `null` clears the window; omit the key to leave it untouched. */
  schedule?: NotificationSchedule | null
}

function toPreferences(raw: PreferencesOut): NotificationPreferences {
  return {
    categories: (raw.categories ?? {}) as CategoryToggles,
    schedule: (raw.schedule as NotificationSchedule | null | undefined) ?? null,
    timezone: raw.timezone ?? null,
  }
}

/**
 * GET /api/v1/notifications/preferences -- category toggles + quiet-hours
 * schedule + read-only timezone context, in one round trip.
 *
 * On a box with no comms configured, this degrades to an honest default
 * (everything enabled, no schedule) rather than erroring -- see
 * notifications/service.py's header. A comms-configured-but-not-yet-synced
 * account, and a genuinely unreachable comms, both surface as a real
 * ApiResponseError (502/504) from api/client.ts -- there is no silent
 * fallback for either, unlike the unconfigured-box case.
 */
export async function getNotificationPreferences(): Promise<NotificationPreferences> {
  const raw = await api.get<PreferencesOut>('/api/v1/notifications/preferences')
  return toPreferences(raw)
}

/**
 * PATCH /api/v1/notifications/preferences -- partial category write
 * and/or full schedule replace/clear. Returns the full updated form.
 */
export async function updateNotificationPreferences(
  patch: NotificationPreferencesPatch,
): Promise<NotificationPreferences> {
  const body: PreferencesPatchIn = {}
  if (patch.categories !== undefined) {
    body.categories = patch.categories
  }
  if ('schedule' in patch) {
    body.schedule = patch.schedule as PreferencesPatchIn['schedule']
  }
  const raw = await api.patch<PreferencesOut>('/api/v1/notifications/preferences', body)
  return toPreferences(raw)
}
