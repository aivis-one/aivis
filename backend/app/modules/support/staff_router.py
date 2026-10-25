# =============================================================================
# AIVIS.ONE Backend -- Support: the operator's routes (T-66, H40, H41)
# =============================================================================
#
#   GET  /api/v1/staff/support/tickets               -- every ticket, with
#     filters: category and rating (both repeatable), status, a day (its
#     edges), a cursor.
#   GET  /api/v1/staff/support/stats                 -- support over a period
#     of appeals: the six categories without spam, the total, spam, and
#     the ratings by the operator each is about (H41).
#   GET  /api/v1/staff/support/tickets/{id}          -- one ticket's card.
#   POST /api/v1/staff/support/tickets/{id}/claim    -- take it.
#   POST /api/v1/staff/support/tickets/{id}/assign   -- hand it over.
#   POST /api/v1/staff/support/tickets/{id}/release  -- back to the pool.
#   POST /api/v1/staff/support/tickets/{id}/status   -- close it one of
#     four ways.
#   POST /api/v1/staff/support/tickets/{id}/reopen   -- back to work.
#   GET  /api/v1/staff/support/operators             -- who to hand it to.
#   GET  /api/v1/staff/support/threads/{id}/messages -- read a ticket or a
#     person's history.
#   POST /api/v1/staff/support/threads/{id}/messages -- reply in a ticket.
#   POST /api/v1/staff/support/threads/{id}/messages/{mid}/translation/retry
#     -- ask again for a message whose translation failed (H39).
#
# `{id}` is always the comms thread id -- of the ticket, or of a person's
# history -- checked against the local pointer before comms is called: a
# guessed or foreign id is a 404.
#
# WHO THE OPERATOR IS comes from get_support_operator and nowhere else:
# `operator` is the session's user id. No handler reads an actor name from
# a request, and the refusals are the user side's: extra="forbid" on every
# body (422), reject_actor_override on the query string (400, naming the
# field). `assignee` in the assign body is the TARGET of a handover, never
# the actor.
#
# Until H40 the list was comms' own queue under GET /threads, scoped by
# comms to the operator; it is gone with no fallback -- the list is our
# table of tickets, and every operator sees every ticket (dependencies.py
# says why).
#
# NOT AVATARING. AvatarSession (staff/models.py) is a staff member
# entering the product AS a user, for repair after a problem is known. It
# has nothing to do with support and is not consulted here; an operator
# acts as themselves, under their own id.
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import BadRequestError
from app.modules.support.dependencies import (
    SupportOperator,
    get_support_operator,
    reject_actor_override,
)
from app.modules.support.schemas import (
    SUPPORT_CLIENT_KEY_MAX_LEN,
    SUPPORT_CLIENT_KEY_PATTERN,
    AssignIn,
    CategoryCode,
    EmptyBodyIn,
    RatingFilterCode,
    SendMessageIn,
    SetTicketStatusIn,
    TicketStatusCode,
)
from app.modules.support.service import (
    assign_ticket,
    claim_support_ticket,
    get_operator_thread_messages,
    get_ticket,
    list_support_operators,
    list_tickets,
    release_ticket,
    reopen_ticket,
    reply_to_support_thread,
    retry_support_translation,
    set_ticket_status,
    support_stats,
)

router = APIRouter(prefix="/api/v1/staff/support", tags=["support-staff"])


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


@router.get("/tickets")
async def list_ticket_rows(
    request: Request,
    # Repeatable: ?category=a&category=b is "a or b". Every value must be
    # a code (422 otherwise); a repeated one counts once.
    category: list[CategoryCode] | None = Query(default=None),
    # H41: by rating, repeatable the same way -- "1".."5", and "none" for a
    # ticket nobody rated.
    rating: list[RatingFilterCode] | None = Query(default=None),
    status: TicketStatusCode | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """Tickets, newest appeal first -- see service.list_tickets. Without
    `status` spam is not listed; `status=spam` is the spam tab.

    `created_from` / `created_to` must carry a time zone (400 otherwise):
    "a day" is the operator's day, and only the screen knows the
    operator's zone -- an edge without one would be read in the server's.
    """
    reject_actor_override(request)
    _require_zones(created_from=created_from, created_to=created_to)
    return await list_tickets(
        session,
        categories=set(category) if category else None,
        ratings=set(rating) if rating else None,
        status=status,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        cursor=cursor,
    )


def _require_zones(**edges: datetime | None) -> None:
    """Each edge given carries a time zone (400 otherwise): "a day" is the
    operator's day, and only the screen knows the operator's zone -- an
    edge without one would be read in the server's."""
    for name, value in edges.items():
        if value is not None and value.tzinfo is None:
            raise BadRequestError(
                f"{name} must carry a time zone", code="support_date_without_zone",
            )


@router.get("/stats")
async def stats(
    request: Request,
    created_from: datetime = Query(),
    created_to: datetime = Query(),
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """Support over the appeals of [created_from, created_to) --
    service.support_stats. Both edges required (422 without one), each
    with a time zone (400), and the period not empty (400)."""
    reject_actor_override(request)
    _require_zones(created_from=created_from, created_to=created_to)
    if created_from >= created_to:
        raise BadRequestError(
            "The period ends before it starts", code="support_period_empty",
        )
    return await support_stats(
        session, created_from=created_from, created_to=created_to,
    )


@router.get("/tickets/{thread_id}")
async def get_ticket_card(
    request: Request,
    thread_id: UUID,
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """One ticket, exactly as a row of GET /tickets. 404 unless
    `thread_id` is a ticket's -- a person's history has no card."""
    reject_actor_override(request)
    return await get_ticket(session, thread_id=thread_id)


@router.post("/tickets/{thread_id}/claim")
async def claim_ticket(
    request: Request,
    thread_id: UUID,
    body: EmptyBodyIn | None = Body(default=None),
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Take a ticket: the act that grants the right to reply. Claiming
    again yourself is a success; one a colleague holds is a 409. Answers
    the card."""
    reject_actor_override(request)
    return await claim_support_ticket(session, operator=operator, thread_id=thread_id)


@router.post("/tickets/{thread_id}/assign")
async def assign(
    request: Request,
    thread_id: UUID,
    body: AssignIn,
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Hand a ticket to another operator (422 unless an active one); the
    new taker is told. Answers the card."""
    reject_actor_override(request)
    return await assign_ticket(
        session, operator=operator, thread_id=thread_id, assignee_id=body.assignee,
    )


@router.post("/tickets/{thread_id}/release")
async def release(
    request: Request,
    thread_id: UUID,
    body: EmptyBodyIn | None = Body(default=None),
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Return a ticket to the pool; every operator is told. Answers the
    card."""
    reject_actor_override(request)
    return await release_ticket(session, operator=operator, thread_id=thread_id)


@router.post("/tickets/{thread_id}/status")
async def set_status(
    request: Request,
    thread_id: UUID,
    body: SetTicketStatusIn,
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Close an OPEN ticket one of four ways; 409 for a ticket that is not
    open or changed meanwhile. Answers the card."""
    reject_actor_override(request)
    return await set_ticket_status(
        session, operator=operator, thread_id=thread_id, status=body.status,
    )


@router.post("/tickets/{thread_id}/reopen")
async def reopen(
    request: Request,
    thread_id: UUID,
    body: EmptyBodyIn | None = Body(default=None),
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Back to work: resolved, rejected or duplicate -- and spam within its
    retention -- back to open. 409 otherwise; 404 once the bin took it.
    Answers the card."""
    reject_actor_override(request)
    return await reopen_ticket(session, operator=operator, thread_id=thread_id)


@router.get("/operators")
async def operators(
    request: Request,
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """Every active support operator -- who a ticket can be handed to."""
    reject_actor_override(request)
    return await list_support_operators(session)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    request: Request,
    thread_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    operator: SupportOperator = Depends(get_support_operator),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Read a ticket or a person's history, newest messages first.

    NOT scoped to tickets this operator took: every operator reads every
    support conversation (dependencies.py). What taking gates is WRITING.

    H39: in the support language -- a person's message as its translation
    with the original beside it, a reply with what the person will read
    (translation.staff_feed). A write session: a message nobody asked a
    translation for yet is queued by this read (the catch-up).
    """
    reject_actor_override(request)
    return await get_operator_thread_messages(
        session, thread_id=thread_id, limit=limit, cursor=cursor,
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
    """Answer the person -- in a ticket you took.

    409 if you have not taken it (comms refuses the write; this says what
    to do), and 409 for a person's history (read-only). Idempotency-Key is
    required: the client's key for this one reply, reused on every retry.
    A write session: the reply's translation is queued with this request.
    """
    reject_actor_override(request)
    return await reply_to_support_thread(
        session,
        operator=operator,
        thread_id=thread_id,
        body=body.body,
        idempotency_key=idempotency_key,
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
