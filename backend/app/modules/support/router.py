# =============================================================================
# AIVIS.ONE Backend -- Support: user-facing routes (T-65)
# =============================================================================
#
#   POST /api/v1/support/threads                    -- open the caller's
#     support conversation, or return the existing one.
#   GET  /api/v1/support/threads                    -- the caller's own
#     conversations, read from the local pointer.
#   POST /api/v1/support/threads/messages           -- send one message
#     into the caller's own conversation. No thread id on the wire.
#   GET  /api/v1/support/threads/{id}/messages      -- that thread's feed.
#   POST /api/v1/support/threads/{id}/read          -- mark it read.
#
# WHO THE CALLER IS COMES FROM THE SESSION, ALWAYS. comms authenticates
# the PRODUCT, not the person, and trusts every actor id it is handed --
# its own handler docstrings call forwarding a client-supplied
# is_supervisor a full read-authz bypass. So the actor names are refused
# on all three surfaces a request has, and each refusal is a different
# mechanism:
#
#   body  -- extra="forbid" on every model (schemas.py) -> 422;
#   query -- _reject_actor_override below -> 400, naming the field;
#   path  -- there is no actor in any path here; the only path parameter
#            is a thread id, and it is checked against the local pointer
#            before comms is called at all (service._require_own_thread).
#
# The query check is explicit rather than implicit because a handler
# that simply does not declare a parameter ignores it in silence: the
# attempt would leave no trace and the guarantee would rest on nobody
# ever adding the parameter later.
#
# STAFF HAVE NO DOOR HERE. The pool side -- claim, reply, close -- is a
# later delivery, and one consequence is visible from this one: a request
# opened today reaches nobody's screen by push. comms' own notifier
# carries the full account of why (KNOWN CEILING, pool-push deferred:
# it cannot resolve the agents of a section without membership); this is
# a pointer to it, not a second copy, so that fixing one does not leave
# the other saying something else.
# =============================================================================

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import BadRequestError
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.support.schemas import EmptyBodyIn, SendMessageIn
from app.modules.support.service import (
    get_support_messages,
    list_support_threads,
    mark_support_thread_read,
    open_support_thread,
    send_support_message,
)
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/support", tags=["support"])

# Every name comms treats as a trusted actor. Listed in full rather than
# per-endpoint: the set is a property of comms' trust model, not of any
# one route, and a name missing from here is a name that would pass.
_ACTOR_PARAMS = (
    "client",
    "sender",
    "participant",
    "operator",
    "assignee",
    "is_supervisor",
)


def _reject_actor_override(request: Request) -> None:
    """400 if the query string carries an actor name.

    Refuses rather than ignores, and names the offender: an attempt to
    act as somebody else should leave a trace in the logs of the person
    who made it, not vanish.
    """
    for name in _ACTOR_PARAMS:
        if name in request.query_params:
            raise BadRequestError(
                f"{name} is derived from the session and cannot be supplied",
                code="actor_override_rejected",
            )


@router.post("/threads")
async def open_thread(
    request: Request,
    body: EmptyBodyIn | None = Body(default=None),
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Open the caller's support conversation, or return the existing one.

    Idempotent by construction: comms returns the same thread for a
    repeated call and the pointer table keeps one row per user. Safe to
    call before every send.

    get_current_user_write (TD-029): this route writes the pointer, so
    the user is loaded on the same write session the write uses.
    """
    _reject_actor_override(request)
    return await open_support_thread(session, user=user)


@router.get("/threads")
async def list_threads(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """The caller's own conversations.

    Answered from the local pointer; comms is asked only for the unread
    counts, and the list still answers without them if comms is down.
    Not paginated: the shape of this channel is one conversation per
    user (see service.py), and a cursor over one row would be a promise
    the data cannot break.
    """
    _reject_actor_override(request)
    return await list_support_threads(session, user=user)


# Declared ABOVE the /{thread_id} routes: a literal segment must not be
# reachable as a thread id. Nothing shadows it today -- there is no bare
# POST /threads/{thread_id} -- and the ordering is what keeps that true
# when one is added.
@router.post("/threads/messages")
async def send_message(
    request: Request,
    body: SendMessageIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """Send one message into the caller's own conversation.

    404 if the caller has never opened it. A reader session on purpose:
    this route writes nothing locally -- the message lives in comms --
    and a write session would open a transaction with nothing in it.
    """
    _reject_actor_override(request)
    return await send_support_message(session, user=user, body=body.body)


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    request: Request,
    thread_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """One of the caller's own threads, newest messages first.

    404 if `thread_id` is not this caller's -- including when it names a
    perfectly real thread belonging to somebody else. Existence never
    leaks.
    """
    _reject_actor_override(request)
    return await get_support_messages(
        session, user=user, thread_id=thread_id, limit=limit, cursor=cursor,
    )


@router.post("/threads/{thread_id}/read")
async def mark_thread_read(
    request: Request,
    thread_id: UUID,
    body: EmptyBodyIn | None = Body(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """Mark the caller's thread read; returns the fresh unread count.

    The read pointer belongs to comms, so nothing is written locally
    here either -- hence the reader session, same as the feed.
    """
    _reject_actor_override(request)
    return await mark_support_thread_read(
        session, user=user, thread_id=thread_id
    )
