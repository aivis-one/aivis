# =============================================================================
# AIVIS.ONE Backend -- Support: the person's routes (T-65, H40)
# =============================================================================
#
#   POST /api/v1/support/tickets   -- an appeal through the form: a topic
#     and the text -> a new ticket and its first message.
#   POST /api/v1/support/messages  -- a message written in the
#     conversation: into the latest open ticket, else the latest ticket,
#     else a new ticket "other" (service.send_dialog_message).
#   GET  /api/v1/support/messages  -- the conversation: every support
#     thread of the caller, history and tickets, glued into one feed.
#   POST /api/v1/support/read      -- read up to now, in every thread.
#   GET  /api/v1/support/unread    -- what is unread, summed over them.
#
# NO THREAD ID ON ANY OF THESE. The person has one conversation however
# many tickets it holds, and its threads are read from the local pointer
# table, never from the wire -- so there is no id here for a caller to
# point at somebody else's conversation. (Until H40 these routes took a
# thread id under /threads/{id}; they are gone, with no fallback.)
#
# WHO THE CALLER IS COMES FROM THE SESSION, ALWAYS. comms authenticates
# the PRODUCT, not the person, and trusts every actor id it is handed. So
# the actor names are refused on the two surfaces a request has here:
#
#   body  -- extra="forbid" on every model (schemas.py) -> 422;
#   query -- reject_actor_override -> 400, naming the field.
#
# STAFF WORK THE OTHER SIDE THROUGH staff_router.py.
# =============================================================================

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.support.dependencies import reject_actor_override
from app.modules.support.schemas import (
    SUPPORT_CLIENT_KEY_MAX_LEN,
    SUPPORT_CLIENT_KEY_PATTERN,
    EmptyBodyIn,
    SendMessageIn,
    TicketIn,
)
from app.modules.support.service import (
    client_support_messages,
    create_ticket,
    mark_support_read,
    send_dialog_message,
    support_unread,
)
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/support", tags=["support"])


def _key_header() -> Any:
    """The client's Idempotency-Key for one press of "send" -- required,
    bounded and of a closed alphabet (schemas.py says why)."""
    return Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=SUPPORT_CLIENT_KEY_MAX_LEN,
        pattern=SUPPORT_CLIENT_KEY_PATTERN,
    )


@router.post("/tickets")
async def open_ticket(
    request: Request,
    body: TicketIn,
    idempotency_key: str = _key_header(),
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """An appeal through the support form: `{ticket, message}`.

    Every submit is a new ticket, even with one open; a retry under the
    same Idempotency-Key is the same ticket and the same message. An
    unknown topic is a 422 before comms is called. A write session: the
    ticket, its translation job and the operator signal commit together
    (get_current_user_write, TD-029).
    """
    reject_actor_override(request)
    return await create_ticket(
        session,
        user=user,
        topic=body.topic,
        body=body.body,
        idempotency_key=idempotency_key,
    )


@router.post("/messages")
async def send_message(
    request: Request,
    body: SendMessageIn,
    idempotency_key: str = _key_header(),
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """A message written in the conversation, not through the form: it
    goes to the latest open ticket, else the latest ticket (back to work),
    else opens a ticket "other". Answers comms' message."""
    reject_actor_override(request)
    return await send_dialog_message(
        session, user=user, body=body.body, idempotency_key=idempotency_key,
    )


@router.get("/messages")
async def get_messages(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """The caller's conversation, newest first, `{items, next_cursor}`.

    H39: every staff reply comes in the caller's language or as a state
    without text (translation.render_for_client). A write session: a
    reply nobody asked a translation for yet is queued by this read (the
    catch-up). A malformed cursor is a 400.
    """
    reject_actor_override(request)
    return await client_support_messages(
        session, user=user, limit=limit, cursor=cursor,
    )


@router.post("/read")
async def mark_read(
    request: Request,
    body: EmptyBodyIn | None = Body(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """Read up to now in the whole conversation; returns what is still
    unread. The read pointers are comms', so nothing is written locally --
    hence the reader session."""
    reject_actor_override(request)
    return await mark_support_read(session, user=user)


@router.get("/unread")
async def unread(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> Any:
    """`{unread}`: what the caller has not read in their conversation --
    the badge of the Support row. 0 for a person with no conversation."""
    reject_actor_override(request)
    return await support_unread(session, user=user)
