# =============================================================================
# AIVIS.ONE Backend -- Notifications inbox: user-facing routes (Phase 6)
# =============================================================================
#
#   GET  /api/v1/notifications                 -- the bell feed, newest
#     first, plus the unread badge in the same round trip.
#   GET  /api/v1/notifications/unread-count    -- the badge alone, for
#     cheap polling.
#   POST /api/v1/notifications/read-all        -- mark every unread
#     delivery read; returns the fresh badge.
#   POST /api/v1/notifications/{id}/read       -- mark one delivery
#     read (idempotent); returns the fresh badge.
#   GET  /api/v1/notifications/preferences     -- category toggles +
#     quiet-hours schedule + read-only timezone context (TASK-38).
#   PATCH /api/v1/notifications/preferences    -- partial category
#     write and/or full schedule replace/clear (TASK-38, avatar-blocked
#     -- see below).
#
# WHO THE CALLER IS COMES FROM THE SESSION, ALWAYS -- see the module
# header on notifications/service.py for the trust-model requirement
# this enforces. There is no recipient/user id anywhere on this router:
# not a body (none of these verbs take one), not a query parameter, not
# a path segment beyond the delivery id being acted on. Every endpoint
# behind get_current_user (any authenticated role -- this is not
# role-gated, every signed-in user has an inbox and preferences).
#
# AVATAR GUARD ON THE PATCH ONLY (TASK-38, an adversarial review of this
# module's first draft caught the gap): muting withdrawals/kyc/payments
# categories is a MUTATION that PERSISTS past the avatar session and
# specifically suppresses the channel the real account owner would use
# to notice unauthorized activity on their money or identity -- the
# same "outlasts impersonation, harms the real owner, no legitimate
# destructive use case" shape logout_all/revoke_session are already
# guarded for, not the read-only-visibility shape GET /sessions is
# deliberately left unguarded for. forbid_avatar() internally depends
# on get_current_user_write (see avatar_guard.py's own docstring) --
# update_notification_preferences below takes get_current_user_write
# directly as its own `user` dependency (not the plain get_current_user
# every other verb here uses) so FastAPI resolves the user ONCE, not
# via two separate cached dependency instances.
#
# /read-all and /preferences ARE DECLARED ABOVE /{delivery_id}/read
# even though none of these paths can actually collide (one segment
# each vs. two after the prefix): the ordering habit from
# support/router.py -- literal segments before a parametrised one --
# is kept here so the next route added to this file does not have to
# re-derive that FastAPI resolves routes in declaration order.
# =============================================================================

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.auth.avatar_guard import forbid_avatar
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.notifications.schemas import (
    InboxPageOut,
    PreferencesOut,
    PreferencesPatchIn,
    UnreadCountOut,
)
from app.modules.notifications.service import (
    get_inbox,
    get_preferences,
    get_unread_count,
    mark_all_read,
    mark_read,
    update_preferences,
)
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=InboxPageOut)
async def list_inbox(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    user: User = Depends(get_current_user),
) -> InboxPageOut:
    """The caller's own inbox -- newest-first, cursor-paginated."""
    return await get_inbox(user=user, limit=limit, cursor=cursor)


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(
    user: User = Depends(get_current_user),
) -> UnreadCountOut:
    """The badge alone, for polling without paying for the feed."""
    return await get_unread_count(user=user)


@router.post("/read-all", response_model=UnreadCountOut)
async def read_all(
    user: User = Depends(get_current_user),
) -> UnreadCountOut:
    """Mark every unread delivery read; returns the fresh badge."""
    return await mark_all_read(user=user)


@router.get("/preferences", response_model=PreferencesOut)
async def get_notification_preferences(
    user: User = Depends(get_current_user),
) -> PreferencesOut:
    """The caller's own preferences -- category toggles, quiet-hours
    schedule, read-only timezone context. See
    notifications/service.py's header for what a comms-configured 404
    (no recipient row yet) and an unconfigured box each answer with."""
    return await get_preferences(user=user)


@router.patch(
    "/preferences",
    response_model=PreferencesOut,
    # R49: an avatar must not be able to mute the categories the real
    # owner would rely on to notice unauthorized money/identity
    # activity -- see the router header note above.
    dependencies=[Depends(forbid_avatar("mute_notifications"))],
)
async def update_notification_preferences(
    patch: PreferencesPatchIn,
    user: User = Depends(get_current_user_write),
) -> PreferencesOut:
    """Partial write: listed category toggles change; `schedule`, when
    present, fully replaces the quiet-hours window (or clears it, on an
    explicit null). Returns the full updated form."""
    return await update_preferences(user=user, patch=patch)


@router.post("/{delivery_id}/read", response_model=UnreadCountOut)
async def read_one(
    delivery_id: UUID,
    user: User = Depends(get_current_user),
) -> UnreadCountOut:
    """Mark one delivery read (idempotent); returns the fresh badge."""
    return await mark_read(user=user, delivery_id=delivery_id)
