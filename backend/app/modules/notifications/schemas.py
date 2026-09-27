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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
# Preferences (TASK-38 item 4; schedule reworked H23 P-114)
# =============================================================================
#
# TWO FORMS OF ONE SCHEDULE. The settings screen offers QUIET HOURS: one
# window {from, to, days} in which the person does not want to be
# disturbed. comms stores the opposite: a list of ALLOWED periods
# [{day, from, to}], one day per period, never crossing midnight (its
# deploy/INTEGRATION.md, section 6 -- "a screen built as quiet hours must
# convert to this form before it writes -- sending its quiet window as-is
# would store the opposite of what the person chose"). The conversion
# lives in ONE place, notifications/schedule.py; these models are the
# screen's form, and nothing in them is ever sent to comms as-is.
#
# `from` is a Python keyword, hence `from_` + Field(alias="from").
# ScheduleIn is a CLIENT REQUEST (extra="forbid" -- an unknown key must
# 422 here rather than be dropped). It is validated HERE, completely:
# comms no longer sees this form, so nobody downstream would catch a
# malformed time or day.
# =============================================================================

_TIME_PATTERN = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"

# comms' day codes, in week order -- the order the conversion walks.
DAY_CODES: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class ScheduleIn(BaseModel):
    """Quiet hours as the CLIENT sends them -- always a full replace.

    `days` are the days the window STARTS on. A window whose `to` is
    earlier than its `from` runs past midnight into the next day
    (sun into mon). `from == to` is refused: it names no window at all,
    and reading it as "the whole day" would be a guess.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(alias="from", pattern=_TIME_PATTERN)
    to: str = Field(pattern=_TIME_PATTERN)
    days: list[str] = Field(min_length=1)

    @field_validator("days")
    @classmethod
    def _known_distinct_days(cls, days: list[str]) -> list[str]:
        unknown = sorted(set(days) - set(DAY_CODES))
        if unknown:
            raise ValueError(f"unknown day(s): {', '.join(unknown)}")
        if len(set(days)) != len(days):
            raise ValueError("a day is listed twice")
        return days

    @model_validator(mode="after")
    def _window_is_not_empty(self) -> "ScheduleIn":
        if self.from_ == self.to:
            raise ValueError("from and to are equal: the window is empty")
        return self


class ScheduleOut(BaseModel):
    """Quiet hours as the screen reads them back -- converted from comms'
    allowed periods by notifications/schedule.py, never comms' own shape.
    """

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    days: list[str]


class PreferencesPatchIn(BaseModel):
    """PATCH /api/v1/notifications/preferences request body.

    extra="forbid" at this level too -- rejects a stray "timezone" (or
    any typo) with a 422 from THIS product's own validation, before a
    round trip to comms is spent proving the same thing. The field set
    is comms' PreferencesPatch; `schedule` is in the SCREEN's form (a
    quiet window) and is converted before it is sent -- see
    notifications/service.py::update_preferences for how `categories`
    (partial) and `schedule` (full-replace-or-clear, presence-sensitive
    via model_fields_set) are forwarded.
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
