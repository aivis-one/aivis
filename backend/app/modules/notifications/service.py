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
    CommsUnavailableError,
    comms_configured,
    comms_request,
)
from app.modules.notifications.schemas import InboxPageOut, UnreadCountOut
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
