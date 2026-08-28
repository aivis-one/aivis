# =============================================================================
# AIVIS.ONE Backend -- Notifications inbox: wire schemas (Phase 6)
# =============================================================================
#
# Response shapes ONLY, mirroring support/schemas.py's split -- comms'
# inbox API (D:/02_Projects/comms/app/api/inbox.py) is a FROZEN CONTRACT,
# and these models are that contract typed for this product rather than
# forwarded as raw dicts. Typing it (instead of `-> Any` the way
# support/router.py forwards comms' payload untouched) is deliberate
# here: generated.ts needs a real interface to hand the frontend, and
# support's threads/messages endpoints -- which stay `Any` -- do not
# have a frontend consumer generated from them yet in this codebase's
# current state.
#
# extra="ignore" rather than "forbid": these are INBOUND shapes (comms'
# answer, not a client request), so an extra field comms adds later
# must not turn into a 502 on every request the day it ships.
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationActionOut(BaseModel):
    """Navigational intent for one inbox item, or nothing.

    comms' frozen contract calls this `action_data`: {"action": ...,
    "params": {...}} | null. None of AIVIS's 16 event producers
    populate it today (checked at the emit_event call sites, e.g.
    withdrawals/service.py ~line 117 -- the payload carries no
    action_data key at all), so every item this proxy serves right now
    has it as null. Typed here anyway: comms may start sending it at
    any point and an untyped field showing up later would be a schema
    break for the frontend, not a feature. Wiring an actual navigation
    target from `action` + `params` is explicitly out of scope --
    see the module header on notifications/service.py.
    """

    model_config = ConfigDict(extra="ignore")

    action: str
    params: dict[str, Any] = {}


class NotificationItemOut(BaseModel):
    """One row of the bell feed -- comms' delivery, typed."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    type: str
    title: str
    body: str
    action_data: NotificationActionOut | None = None
    priority: int
    sent_at: datetime
    read_at: datetime | None = None
    created_at: datetime


class InboxPageOut(BaseModel):
    """GET /api/v1/notifications -- newest-first feed plus the badge.

    `unread` rides along in the same round trip as comms' own contract
    promises, so a page render never needs a second call just to paint
    the badge next to the list it is already fetching.
    """

    model_config = ConfigDict(extra="ignore")

    items: list[NotificationItemOut]
    next_cursor: str | None = None
    unread: int


class UnreadCountOut(BaseModel):
    """The badge alone -- GET /unread-count and both mark-read verbs."""

    model_config = ConfigDict(extra="ignore")

    unread: int
