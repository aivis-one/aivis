# =============================================================================
# AIVIS.ONE Backend -- Support: who the operator is (T-66, H40)
# =============================================================================
#
# ONE place answers "may this person work support". Every operator-side
# route takes its identity from here and computes nothing itself -- comms
# trusts whatever `operator` it is handed, so a second place computing it
# is a second place that can get it wrong.
#
# WHAT IS CHECKED, AND WHERE THE CHECK ALREADY LIVED. Role, the existence
# of a staff profile and its is_active flag are get_current_staff's
# business (auth/dependencies.py) and are NOT re-implemented here: a
# private copy of "who counts as staff" would drift from the original the
# first time the original changed.
#
# AN OPERATOR IS ANY ACTIVE STAFF MEMBER, AND EVERY OPERATOR READS EVERY
# SUPPORT CONVERSATION. This is the owner's decision (H40 gate), not a
# gap: since H40 the operator's list is our own table of tickets, and
# every operator sees every ticket and its conversation -- a person's
# history included -- as velo's admins do. What used to narrow the read
# is gone with it: comms' queue scoped a plain operator to the unclaimed
# pool and their own threads, and `is_supervisor` (the product's admin
# mark) widened that scope to everything; neither the comms queue nor the
# flag is read any more, so the flag was removed rather than left as a
# switch that switches nothing. Who may WRITE is still narrower and still
# comms': only the operator who took a ticket replies in it
# (support/service.py, reply_to_support_thread).
#
# The same people are comms' section roster and its operators group --
# declared in one place, service.emit_support_membership, when a staff
# member is promoted or deactivated.
# =============================================================================

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.exceptions import BadRequestError
from app.modules.auth.dependencies import get_current_staff
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
# `is_supervisor` stays refused although nothing reads it any more: it is
# a name comms trusts (its thread list), and a request carrying it is an
# attempt to widen a read, worth a trace whether or not it would work.


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
    """A verified support operator.

    Frozen: decided once, at the edge of the request -- a handler cannot
    turn itself into somebody else.
    """

    user: User

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
    """
    user = await get_current_staff(request, session)

    return SupportOperator(user=user)
