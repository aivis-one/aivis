# =============================================================================
# AIVIS.ONE Backend -- Support: operator-facing routes (T-66)
# =============================================================================
#
#   GET  /api/v1/staff/support/threads              -- the queue: the
#     unclaimed pool plus this operator's own threads (a supervisor gets
#     every thread there is).
#   POST /api/v1/staff/support/threads/{id}/claim   -- take one.
#   GET  /api/v1/staff/support/threads/{id}/messages -- read it.
#   POST /api/v1/staff/support/threads/{id}/messages -- reply.
#   POST /api/v1/staff/support/threads/{id}/status  -- resolve or close.
#
# THE STAKE HERE IS HIGHER THAN ON THE USER SIDE. A wrong actor there
# would open one person's conversation to one other person; a wrong
# `is_supervisor` here opens every conversation of every user at once,
# because comms skips its scope filter entirely when that flag is true
# and does not verify it (it cannot -- it has no role registry).
#
# So both trusted values come from get_support_operator and nowhere else:
# `operator` is the session's user id, `is_supervisor` is resolved from
# the staff profile. No handler in this file reads either name, and none
# accepts a parameter that could carry one -- the refusals are the same
# three mechanisms as on the user side: extra="forbid" on every body
# (422), reject_actor_override on the query string (400, naming the
# field), and no actor in any path. The one path parameter is a thread
# id, checked against the local pointer before comms is called.
#
# NOT AVATARING. AvatarSession (staff/models.py) is a staff member
# entering the product AS a user, for repair after a problem is known.
# It has nothing to do with this queue and is not consulted anywhere in
# this file; an operator here acts as themselves, under their own id.
# =============================================================================

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.modules.support.dependencies import (
    SupportOperator,
    get_support_operator,
    reject_actor_override,
)
from app.modules.support.schemas import (
    EmptyBodyIn,
    SendMessageIn,
    SetStatusIn,
)
from app.modules.support.service import (
    claim_support_thread,
    get_operator_thread_messages,
    list_operator_threads,
    reply_to_support_thread,
    set_support_thread_status,
)

router = APIRouter(prefix="/api/v1/staff/support", tags=["support-staff"])


@router.get("/threads")
async def list_threads(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    operator: SupportOperator = Depends(get_support_operator),
) -> Any:
    """The operator's queue, most recently active first.

    What comes back is decided by comms' own visibility rule, not by a
    filter here: a plain operator sees the unclaimed pool and the threads
    they claimed; a supervisor sees everything. Pool rows carry no unread
    count -- nobody takes part in them yet.
    """
    reject_actor_override(request)
    return await list_operator_threads(
        operator=operator, limit=limit, cursor=cursor
    )


@router.post("/threads/{thread_id}/claim")
async def claim_thread(
    request: Request,
    thread_id: UUID,
    body: EmptyBodyIn | None = Body(default=None),
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """Take an unclaimed request; the act that grants the right to reply.

    Claiming again yourself is a success and changes nothing. Claiming
    one a colleague already took is a 409 -- an answer, not a failure.

    A reader session: nothing is written locally here. Who owns a thread
    is comms' state, and keeping a copy of it in this database would be a
    copy that goes stale (see service.py).
    """
    reject_actor_override(request)
    return await claim_support_thread(
        session, operator=operator, thread_id=thread_id
    )


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    request: Request,
    thread_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """Read one known request, newest messages first.

    404 if the id names no support thread this product created --
    decided here, before comms is asked anything about it.

    NOT scoped to threads this operator claimed, deliberately: the queue
    shows the unclaimed pool, and an operator has to read a request
    before deciding to take it. What claiming gates is WRITING (comms
    refuses a message from anyone but the assignee) -- reading is gated
    by being an operator at all.
    """
    reject_actor_override(request)
    return await get_operator_thread_messages(
        session, thread_id=thread_id, limit=limit, cursor=cursor
    )


@router.post("/threads/{thread_id}/messages")
async def reply_to_thread(
    request: Request,
    thread_id: UUID,
    body: SendMessageIn,
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """Answer the person who opened this request.

    409 if the operator has not claimed it -- comms refuses the write and
    this is that refusal, said in a way the caller can act on. A
    supervisor gets the same 409: reading everything is not writing
    everything.
    """
    reject_actor_override(request)
    return await reply_to_support_thread(
        session, operator=operator, thread_id=thread_id, body=body.body
    )


@router.post("/threads/{thread_id}/status")
async def set_thread_status(
    request: Request,
    thread_id: UUID,
    body: SetStatusIn,
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """Resolve or close a request.

    Only forward moves exist (see schemas.SetStatusIn): a closed thread
    comes back only when the client writes into it. Closing also sends
    the client comms' "your request was closed" notice.
    """
    reject_actor_override(request)
    return await set_support_thread_status(
        session,
        operator=operator,
        thread_id=thread_id,
        status=body.status,
    )
