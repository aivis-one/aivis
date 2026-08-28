# =============================================================================
# AIVIS.ONE Backend -- Notifications inbox: the bell (Phase 6 proxy)
# =============================================================================
#
# A PROXY, not a store -- and thinner than support/service.py's user
# side: there is no local pointer table at all, because there is
# nothing here for this product to own. comms' inbox API
# (D:/02_Projects/comms/app/api/inbox.py) already IS a per-user table
# keyed by recipient_id, and recipient_id IS user.id 1:1 -- confirmed
# by core/comms_sync.ensure_recipient, which upserts recipients keyed
# on user.id and nothing else. So every read and every write this
# module makes is one HTTP call to comms; nothing is cached, nothing is
# joined, nothing is written to this product's own database.
#
# THE TRUST-MODEL REQUIREMENT (comms' own file header, its Phase 6
# note): comms does NOT verify that recipient_id belongs to the calling
# end user -- the shared service token authenticates the PRODUCT, not
# the person, exactly as core/comms.py's module header describes for
# every other comms-touching call in this tree. So `user.id` is read
# from `get_current_user`'s session ONLY, everywhere in this module.
# There is no recipient/user id parameter anywhere on these functions
# or on notifications/router.py -- not in a body, not in a query, not
# in a path segment -- so there is nothing for a caller to override.
#
# WHY COMMS-DOWN IS HANDLED DIFFERENTLY HERE THAN ON support's LIST.
#
#   NOT CONFIGURED (comms_configured() is False) is a supported box
#   state -- local dev, CI, a deployment that has not stood up comms
#   yet -- and it is permanent for as long as that box has no comms
#   address, not a one-off blip. Every function below answers as if
#   the inbox were empty (zero unread, no items; the two mark-read
#   verbs are no-ops that report zero) instead of a 502 on every page
#   load and every 30s poll for the life of that deployment. This is
#   the one place in this product that manufactures a zero for a
#   comms-backed count on purpose, and the justification is narrow:
#   "not configured" means "this box has no bell", and an empty bell
#   is the honest rendering of that -- not a lie about unread state
#   comms never had a chance to hold.
#
#   CONFIGURED BUT UNREACHABLE / REJECTED / TIMED OUT is the opposite
#   case -- a real failure of a service this box expects to be up --
#   and here nothing is swallowed. Unlike support's list, which still
#   has local rows to answer from when comms cannot add unread counts
#   (see support/service.py:list_support_threads), this module has NO
#   local data to fall back to: the inbox IS comms' answer, not an
#   enrichment on top of something else. Degrading to an empty page or
#   a zero badge here would not be honest degradation, it would be
#   fabricating "nothing to see" for a user who may have unread items
#   sitting behind an outage. So comms_request's typed AivisError is
#   left to propagate to main.py's handler exactly as it does for
#   support's send/read calls (a person pressed something and is owed
#   the true outcome) -- and the frontend treats a failed poll the way
#   it treats any other transient read failure: keep the last known
#   badge value on screen and try again next cycle, never reset it to
#   zero on an error.
# =============================================================================

from uuid import UUID

import structlog
from pydantic import ValidationError

from app.core.comms import (
    CommsRejectedError,
    CommsUnavailableError,
    comms_configured,
    comms_request,
)
from app.modules.notifications.schemas import (
    InboxPageOut,
    PreferencesOut,
    PreferencesPatchIn,
    UnreadCountOut,
)
from app.modules.users.models import User

logger = structlog.get_logger()

_INBOX_PATH_TMPL = "/api/v1/recipients/{recipient_id}/inbox"

# Built once, reused for every "no comms on this box" answer -- see the
# module header on why this is the one place a zero is manufactured.
_EMPTY_PAGE = InboxPageOut(items=[], next_cursor=None, unread=0)
_ZERO_UNREAD = UnreadCountOut(unread=0)


def _inbox_path(user: User, suffix: str = "") -> str:
    """comms' inbox path for THIS caller, and only this caller.

    The only place user.id is read in this module -- every function
    below calls through here, so there is exactly one line that turns
    a session into a comms path rather than one per verb that could
    drift apart.
    """
    return f"{_INBOX_PATH_TMPL.format(recipient_id=user.id)}{suffix}"


def _malformed(what: str, user: User, payload: object) -> CommsUnavailableError:
    """comms' answer is input too (support/service.py's rule, applied
    here): a shape pydantic cannot parse must come out as a clean 502,
    not a 500 on a request behind a badge someone is looking at."""
    logger.error(
        "comms_inbox_payload_malformed",
        what=what,
        user_id=str(user.id),
        payload_type=type(payload).__name__,
    )
    return CommsUnavailableError()


async def get_inbox(
    *, user: User, limit: int, cursor: str | None
) -> InboxPageOut:
    """The bell feed: newest-first items plus the badge, one round trip."""
    if not comms_configured():
        return _EMPTY_PAGE

    params: dict[str, object] = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    payload = await comms_request(
        "GET", _inbox_path(user), params=params
    )
    try:
        return InboxPageOut.model_validate(payload)
    except ValidationError:
        raise _malformed("inbox", user, payload) from None


async def get_unread_count(*, user: User) -> UnreadCountOut:
    """Cheap badge polling -- the counter alone, no items."""
    if not comms_configured():
        return _ZERO_UNREAD

    payload = await comms_request("GET", _inbox_path(user, "/unread-count"))
    try:
        return UnreadCountOut.model_validate(payload)
    except ValidationError:
        raise _malformed("unread_count", user, payload) from None


async def mark_read(*, user: User, delivery_id: UUID) -> UnreadCountOut:
    """Mark one delivery read (idempotent); returns the fresh badge.

    404s (delivery absent, or not this caller's) come back from
    comms_request as CommsRejectedError -- a real, per-request answer,
    forwarded as-is rather than folded into "comms is down".
    """
    if not comms_configured():
        return _ZERO_UNREAD

    payload = await comms_request(
        "POST", _inbox_path(user, f"/{delivery_id}/read")
    )
    try:
        return UnreadCountOut.model_validate(payload)
    except ValidationError:
        raise _malformed("mark_read", user, payload) from None


async def mark_all_read(*, user: User) -> UnreadCountOut:
    """Mark every unread in_app delivery read; returns the fresh badge."""
    if not comms_configured():
        return _ZERO_UNREAD

    payload = await comms_request("POST", _inbox_path(user, "/read-all"))
    try:
        return UnreadCountOut.model_validate(payload)
    except ValidationError:
        raise _malformed("mark_all_read", user, payload) from None


# =============================================================================
# Preferences (TASK-38 item 4) -- comms/app/api/prefs.py, FROZEN CONTRACT
# =============================================================================
#
# Same proxy discipline as the inbox above: no local table, `user.id`
# read from the session only (never accepted from client input --
# comms' own header on this endpoint repeats the trust-model
# requirement verbatim), one path builder so there is exactly one line
# that turns a session into a comms path.
#
# WHY THE 404 CASE IS *NOT* HANDLED THE INBOX'S WAY.
#
#   The inbox's not-configured/down split (this module's top header)
#   does not fully cover preferences, because preferences has a THIRD
#   failure shape the inbox does not: a 404 from comms *while comms is
#   configured and reachable*, meaning "this user has no recipient row
#   yet" (registration's synchronous upsert failed and the outbox
#   relay has not caught up -- see core/comms.py's own module header).
#   comms' prefs.py is explicit that this is not the inbox's "empty"
#   case: "preferences of a nonexistent recipient are not empty --
#   there is no row to hang them on". Fabricating a plausible-looking
#   "everything enabled" page here would be actively misleading in a
#   way the inbox's empty page is not: a GET that lies "here are your
#   settings" followed by a PATCH that then hard-fails against the
#   same missing row (see update_preferences below -- the write cannot
#   silently succeed against a row that isn't there) reads to a user as
#   "it saved, then broke" rather than "this isn't ready yet". So GET's
#   404 is translated to the SAME clean, honest refusal PATCH's 404
#   produces -- deliberately reusing support/service.py's
#   create_thread precedent (its own comment, same failure) rather than
#   inventing a second policy for the same underlying condition.
#
#   comms NOT CONFIGURED on this box (permanent, box-wide -- local dev,
#   CI) is still handled the inbox's way for GET only: an honestly
#   default form (nothing muted, no quiet hours, no timezone) instead
#   of a 502 on every settings-screen load. PATCH does NOT get this
#   fallback: comms_request's default not-configured behaviour (a
#   loud CommsUnavailableError, policy B) is left untouched, because
#   "saving" a preference with nowhere to persist it would be a lie a
#   default GET response is not -- GET shows a state, PATCH promises a
#   write actually happened.
#
# WHY THIS STAYS OFF avatar_guard's RESTRICTED_OPERATIONS.
#   Two independent reasons, either one sufficient on its own:
#     1. Not a money- or identity-mutating action, and not the kind of
#        disruption vector revoke_session/logout_all are (ending a
#        session an avatar has no legitimate reason to touch). Muting
#        a notification category or setting quiet hours affects only
#        what a person is *told*, not what they *have*.
#     2. Structural: forbid_avatar() requires Depends(get_current_user_write)
#        (avatar_guard.py's own docstring on why -- ordering + caching
#        guarantees). This module makes no local DB write on ANY of its
#        verbs, mutating or not (it is a pure comms proxy), which is
#        exactly why mark_read/mark_all_read above -- themselves
#        mutating, from the user's perspective -- already use plain
#        get_current_user rather than get_current_user_write. Guarding
#        just the new PATCH would mean this one verb alone switches
#        dependencies for a guard whose two independent grounds above
#        do not support adding it in the first place.
# =============================================================================

_PREFS_PATH_TMPL = "/api/v1/recipients/{recipient_id}/preferences"

# Mirrors comms-profile/types.yaml's declared category set (see that
# file's own header for the full reasoning behind each one). Used
# ONLY for the two fallback forms below (comms not configured on this
# box; a recipient comms has not synced yet is NOT a fallback case --
# see the header above) -- comms itself is the source of truth for
# this list on every real answer it gives (its own facade emits it off
# `registry.registered_categories()`), this tuple exists purely so an
# honestly-default fallback form has *a* category list to show instead
# of an empty one. Keep in sync with comms-profile/types.yaml if a
# category is ever added there.
_KNOWN_CATEGORIES = (
    "agent_applications",
    "commissions",
    "deposits",
    "installments",
    "kyc",
    "payments",
    "purchases",
    "staff_messages",
    "support_messages",
    "withdrawals",
)


def _prefs_path(user: User) -> str:
    """comms' preferences path for THIS caller, and only this caller.

    The only place user.id is read for preferences -- both functions
    below call through here, matching _inbox_path's discipline above.
    """
    return _PREFS_PATH_TMPL.format(recipient_id=user.id)


def _default_preferences() -> PreferencesOut:
    """The honest answer for a box with no comms to ask: nothing muted,
    no quiet hours, no timezone context to show."""
    return PreferencesOut(
        categories=dict.fromkeys(_KNOWN_CATEGORIES, True),
        schedule=None,
        timezone=None,
    )


def _recipient_not_ready(user: User) -> CommsUnavailableError:
    """comms is up but has no recipient row for this user yet.

    Same translation support/service.py's create_thread applies to the
    identical condition: comms' own wording about a missing recipient
    row is an internal detail, not a message for this user, and the
    502 code marks it as retry-later rather than "you did
    something wrong" -- true on both counts, since the outbox relay
    (core/comms.py) is expected to catch this up on its own.
    """
    logger.warning("comms_prefs_recipient_not_synced", user_id=str(user.id))
    return CommsUnavailableError(
        message="Notification preferences are not ready for this account yet",
        code="comms_recipient_pending",
    )


async def get_preferences(*, user: User) -> PreferencesOut:
    """The settings screen's GET: category toggles + schedule + timezone."""
    if not comms_configured():
        return _default_preferences()

    try:
        payload = await comms_request("GET", _prefs_path(user))
    except CommsRejectedError as exc:
        if exc.status_code == 404:
            raise _recipient_not_ready(user) from exc
        raise
    try:
        return PreferencesOut.model_validate(payload)
    except ValidationError:
        raise _malformed("preferences", user, payload) from None


async def update_preferences(
    *, user: User, patch: PreferencesPatchIn
) -> PreferencesOut:
    """Partial write: listed category toggles change, schedule replaces
    whole (or clears, on an explicit null) -- comms' own PATCH contract,
    forwarded through unconverted.

    `exclude_unset=True` is what makes "clear the schedule" (an
    explicit `schedule: null` in the request) distinct from "leave the
    schedule alone" (the key omitted entirely): pydantic tracks which
    fields the client actually sent (comms' own PreferencesPatch does
    the equivalent check via `model_fields_set` on its side), so a
    field present with value null still serializes, while an absent
    field does not -- exactly the presence-sensitive semantics comms'
    contract requires and PreferencesPatchIn's docstring names.
    """
    body = patch.model_dump(mode="json", by_alias=True, exclude_unset=True)
    try:
        payload = await comms_request("PATCH", _prefs_path(user), json=body)
    except CommsRejectedError as exc:
        if exc.status_code == 404:
            raise _recipient_not_ready(user) from exc
        raise
    try:
        return PreferencesOut.model_validate(payload)
    except ValidationError:
        raise _malformed("preferences_patch", user, payload) from None
