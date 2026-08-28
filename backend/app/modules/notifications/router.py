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
#
# WHO THE CALLER IS COMES FROM THE SESSION, ALWAYS -- see the module
# header on notifications/service.py for the trust-model requirement
# this enforces. There is no recipient/user id anywhere on this router:
# not a body (none of these verbs take one), not a query parameter, not
# a path segment beyond the delivery id being acted on. Every endpoint
# behind get_current_user (any authenticated role -- this is not
# role-gated, every signed-in user has an inbox).
#
# /read-all IS DECLARED ABOVE /{delivery_id}/read even though the two
# paths cannot collide (one segment vs. two after the prefix): the
# ordering habit from support/router.py -- literal segments before a
# parametrised one -- is kept here so the next route added to this file
# does not have to re-derive that FastAPI resolves routes in
# declaration order.
# =============================================================================

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.auth.dependencies import get_current_user
from app.modules.notifications.schemas import InboxPageOut, UnreadCountOut
from app.modules.notifications.service import (
    get_inbox,
    get_unread_count,
    mark_all_read,
    mark_read,
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


@router.post("/{delivery_id}/read", response_model=UnreadCountOut)
async def read_one(
    delivery_id: UUID,
    user: User = Depends(get_current_user),
) -> UnreadCountOut:
    """Mark one delivery read (idempotent); returns the fresh badge."""
    return await mark_read(user=user, delivery_id=delivery_id)
