# =============================================================================
# AIVIS.ONE Backend -- Support: who the operator is (T-66)
# =============================================================================
#
# ONE place answers "may this person work the support queue, and how
# widely". Every operator-side route takes its identity from here and
# computes nothing itself -- comms trusts whatever `operator` and
# `is_supervisor` it is handed, so a second place computing them is a
# second place that can get them wrong.
#
# WHAT IS CHECKED, AND WHERE THE CHECK ALREADY LIVED. Role, the existence
# of a staff profile and its is_active flag are get_current_staff's
# business (auth/dependencies.py) and are NOT re-implemented here: a
# private copy of "who counts as staff" would drift from the original the
# first time the original changed. This module adds exactly one thing on
# top -- how WIDE the read is.
#
# SUPERVISOR IS THE PRODUCT'S EXISTING ADMIN MARK, NOT A NEW PERMISSION.
# is_admin(effective) -- every known permission key present and True --
# is how this codebase already says "this person sees everything"
# (AIVIS-Design-Document 3.10: gradations come from configuration, not
# from extra roles). A dedicated support key was considered and rejected
# for a mechanical reason, recorded here because it is not obvious:
#
#   * a new key defaulting to False demotes EVERY current admin the
#     moment it is added -- is_admin requires every known key to be
#     present and true, and an absent key resolves to False. The endpoint
#     that would grant it (PATCH /staff/users/{id}/permissions) is itself
#     admin-only, so the key would lock the door and stay behind it;
#   * a new key defaulting to True hands every active staff member the
#     read of every user's support conversation, which is a privacy
#     decision nobody made on purpose;
#   * the same drift has already been paid for once here: content_manage
#     reached staff/constants.py without reaching staff/schemas.py and
#     was un-toggglable through the admin UI until someone noticed (see
#     that file's header).
#
# SO: WHOEVER ADDS A TENTH PERMISSION KEY ALSO SILENTLY REVOKES SUPPORT
# SUPERVISION from every admin until the key is set. That property
# belongs to is_admin and predates this module; it is written down here
# because support supervision now rides on it.
#
# Promotion trigger for a dedicated key: a "support lead" who is not an
# admin becomes a real role. Then the key arrives together with
# staff/schemas.py, the admin UI and a decision about is_admin -- one
# deliberate change, not a side effect of this one.
# =============================================================================

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.exceptions import BadRequestError, ForbiddenError
from app.modules.auth.dependencies import get_current_staff
from app.modules.staff.constants import is_admin
from app.modules.staff.service import (
    get_effective_permissions,
    get_staff_profile,
)
from app.modules.users.models import User

# Every name comms treats as a trusted actor. Defined HERE rather than in
# either router so both sides refuse the same set: two copies of this
# tuple would mean the newer route eventually forgets a name.
ACTOR_PARAMS = (
    "client",
    "sender",
    "participant",
    "operator",
    "assignee",
    "is_supervisor",
)


def reject_actor_override(request: Request) -> None:
    """400 if the query string carries an actor name.

    Refuses rather than ignores, and names the offender: an attempt to
    act as somebody else should leave a trace in the logs of the person
    who made it, not vanish.
    """
    for name in ACTOR_PARAMS:
        if name in request.query_params:
            raise BadRequestError(
                f"{name} is derived from the session and cannot be supplied",
                code="actor_override_rejected",
            )


@dataclass(frozen=True)
class SupportOperator:
    """A verified support operator and the width of their read.

    Frozen: the two values are decided once, at the edge of the request,
    and a handler that could edit them would be a handler that could
    widen its own scope.
    """

    user: User
    is_supervisor: bool

    @property
    def id(self) -> UUID:
        """The id comms is given as `operator` -- the session's, always."""
        return self.user.id


async def get_support_operator(
    request: Request,
    session: AsyncSession = Depends(get_db_reader),
) -> SupportOperator:
    """The caller as a support operator, or a refusal.

    Refuses a user who is not staff, has no staff profile, or whose
    profile is deactivated -- all three by way of get_current_staff.

    The profile is then loaded a SECOND time, because get_current_staff
    verifies it and does not return it. One redundant SELECT per
    operator request is the price of not copying the staff policy into
    this module; it is named in the T-66 report rather than optimised
    away here.
    """
    user = await get_current_staff(request, session)

    profile = await get_staff_profile(user.id, session)
    if profile is None:
        # get_current_staff just proved a profile exists, so this is the
        # narrow race where it was deleted between the two reads -- not
        # an impossible branch. Fail closed.
        raise ForbiddenError("Staff profile not found")

    return SupportOperator(
        user=user,
        is_supervisor=is_admin(get_effective_permissions(profile)),
    )
