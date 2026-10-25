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
#   POST /api/v1/staff/support/threads/{id}/messages/{mid}/translation/retry
#     -- ask again for a message whose translation failed (H39).
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

from fastapi import APIRouter, Body, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.support.dependencies import (
    SupportOperator,
    get_support_operator,
    reject_actor_override,
)
from app.modules.support.schemas import (
    SUPPORT_CLIENT_KEY_MAX_LEN,
    SUPPORT_CLIENT_KEY_PATTERN,
    EmptyBodyIn,
    SendMessageIn,
    SetStatusIn,
)
from app.modules.support.service import (
    claim_support_thread,
    get_operator_thread_messages,
    list_operator_threads,
    reply_to_support_thread,
    retry_support_translation,
    set_support_thread_status,
)

router = APIRouter(prefix="/api/v1/staff/support", tags=["support-staff"])


@router.get("/threads")
async def list_threads(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """The operator's queue, most recently active first.

    What comes back is decided by comms' own visibility rule, not by a
    filter here: a plain operator sees the unclaimed pool and the threads
    they claimed; a supervisor sees everything. Pool rows carry no unread
    count -- nobody takes part in them yet.

    A reader session, and it is not for reading a thread: T-75 adds
    `client_profile` to every row it can, which is a local lookup through
    the pointer table. Nothing is written here.
    """
    reject_actor_override(request)
    return await list_operator_threads(
        session, operator=operator, limit=limit, cursor=cursor
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
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Read one known request, newest messages first.

    H39: in the support language -- a person's message as its translation
    with the original beside it, a reply with what the person will read
    (translation.staff_feed). A write session: a message nobody asked a
    translation for yet is queued by this read (the catch-up).

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
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=SUPPORT_CLIENT_KEY_MAX_LEN,
        pattern=SUPPORT_CLIENT_KEY_PATTERN,
    ),
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Answer the person who opened this request.

    A write session since H39: the reply's translation into the person's
    language is queued with this request (translation.py).

    Idempotency-Key is required, as on the user side: the client's key
    for this one reply, reused on every retry of it.

    409 if the operator has not claimed it -- comms refuses the write and
    this is that refusal, said in a way the caller can act on. A
    supervisor gets the same 409: reading everything is not writing
    everything.
    """
    reject_actor_override(request)
    return await reply_to_support_thread(
        session,
        operator=operator,
        thread_id=thread_id,
        body=body.body,
        idempotency_key=idempotency_key,
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

    `open` is not offered (see schemas.SetStatusIn): comms 3.11 has a
    manual return to `open`, and offering it is the ticket work of H40.
    Until then a closed thread comes back when the client writes into
    it. Closing also sends the client comms' "your request was closed"
    notice.
    """
    reject_actor_override(request)
    return await set_support_thread_status(
        session,
        operator=operator,
        thread_id=thread_id,
        status=body.status,
    )


@router.post("/threads/{thread_id}/messages/{message_id}/translation/retry")
async def retry_translation(
    request: Request,
    thread_id: UUID,
    message_id: UUID,
    body: EmptyBodyIn | None = Body(default=None),
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Ask again for a message whose translation's job failed (H39).

    Only after the TRANSPORT failed -- the job ended without an answer.
    409 when the translation is in progress, done, declined (a variant is
    final in comms) or not needed; 404 when the message is not found in
    this thread. Any operator, claimed or not: nothing is posted as
    anyone, the same boundary as reading the thread.
    """
    reject_actor_override(request)
    return await retry_support_translation(
        session, thread_id=thread_id, message_id=message_id,
    )
