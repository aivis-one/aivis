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

from pydantic import BaseModel, ConfigDict, Field


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


# =============================================================================
# Preferences (TASK-38 item 4) -- comms' E8-shaped facade, typed both ways
# =============================================================================
#
# comms' contract (D:/02_Projects/comms/app/api/prefs.py, FROZEN):
#   GET/PATCH .../preferences -> {categories: {<category>: bool, ...},
#   schedule: {from, to, days} | null, timezone: <IANA> | null}. Mirrored
# here as real Pydantic models rather than forwarded as `-> Any` (the
# support module's choice for its still-frontend-less threads/messages
# endpoints) because this DOES have a frontend consumer -- generated.ts
# needs a real interface, same reasoning notifications/schemas.py's own
# header gives for InboxPageOut / UnreadCountOut above.
#
# `from` is a Python keyword, hence `from_` + Field(alias="from") on both
# the inbound and outbound schedule shapes -- exactly comms' own
# ScheduleIn does it. Two separate schedule classes rather than one
# reused both ways: ScheduleIn is a CLIENT REQUEST (extra="forbid" --
# an unknown key, most importantly "timezone", must 422 immediately
# rather than being silently dropped and round-tripped to comms as a
# request that looks like it worked); ScheduleOut is comms' ANSWER
# (extra="ignore" -- comms adding a field later must not 502 every
# request the day it ships, same rule InboxPageOut's header states).
# =============================================================================


class ScheduleIn(BaseModel):
    """Quiet-hours window as the CLIENT sends it -- always a full replace.

    All three fields are required when `schedule` is present at all
    (comms' contract: PATCH .../preferences' schedule key is FULL
    REPLACE, never a partial merge). Local time strings, "HH:MM" --
    left as `str` rather than `datetime.time` deliberately: this proxy
    does not re-validate the format, comms already does (a malformed
    string round-trips to comms and comes back as a 422 CommsRejectedError,
    forwarded as-is), and a plain string is what `<input type="time">`
    on the frontend already produces without any local conversion.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    days: list[str]


class ScheduleOut(BaseModel):
    """Quiet-hours window as comms answers it -- same shape, read-only side."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    days: list[str]


class PreferencesPatchIn(BaseModel):
    """PATCH /api/v1/notifications/preferences request body.

    extra="forbid" at this level too -- rejects a stray "timezone" (or
    any typo) with a 422 from THIS product's own validation, before a
    round trip to comms is spent proving the same thing. Mirrors
    comms' own PreferencesPatch field-for-field; see
    notifications/service.py's header for how `categories` (partial)
    and `schedule` (full-replace-or-clear, presence-sensitive via
    model_fields_set) are forwarded.
    """

    model_config = ConfigDict(extra="forbid")

    categories: dict[str, bool] | None = None
    schedule: ScheduleIn | None = None


class PreferencesOut(BaseModel):
    """GET /api/v1/notifications/preferences and the PATCH round-trip.

    `timezone` is READ-ONLY context (comms' own contract: sync-owned,
    rejected with 422 if a client tries to set it) -- present here only
    so the settings screen can caption the schedule with it.
    """

    model_config = ConfigDict(extra="ignore")

    categories: dict[str, bool]
    schedule: ScheduleOut | None = None
    timezone: str | None = None
