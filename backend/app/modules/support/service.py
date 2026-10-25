# =============================================================================
# AIVIS.ONE Backend -- Support: tickets, the person's conversation, the
# operator's work, the rating (T-65, T-66, H39, H40, H41)
# =============================================================================
#
# WHAT SUPPORT IS, SINCE H40 (owner rulings, the H40 handoff, section 1):
#
#   EVERY APPEAL THROUGH THE FORM IS A TICKET -- a new one even when an
#   earlier ticket is open: its own comms thread of kind `ticket` in the
#   support section, a topic and a category as codes (models.TOPICS), our
#   status. The message goes in as written -- no topic in its text.
#
#   FOR THE PERSON IT IS ONE CONVERSATION: their support threads -- the
#   pre-H40 `dm` history and every ticket -- are glued into one feed by
#   time (client_support_messages), read and counted together, and
#   replies are signed "Support", never with an operator's name. A message
#   written in the conversation goes to their latest OPEN ticket, else to
#   their latest ticket (returning it to work), else opens a ticket
#   "other" (send_dialog_message).
#
#   STATUSES ARE OURS, comms KNOWS TWO: an operator moves an OPEN ticket to
#   resolved / rejected / duplicate / spam, and the thread to comms'
#   `resolved`; "back to work" moves both back to `open`. Nothing moves a
#   thread to `closed` -- comms would tell the person, and its auto-close
#   is off on our boxes (THREAD_AUTO_CLOSE_DAYS=0, the installer). A
#   person's message reopens the ticket -- except SPAM, which stays spam,
#   translates nothing and signals nobody.
#
#   THE OPERATOR SIGNAL: support.message_received on every message a
#   person sends -- to the operator who took the ticket, else to every
#   operator (the comms group support_operators); and a signal on every
#   handover (assign: to the new taker; release: to everybody).
#
#   THE RATING (H41): resolving a ticket records who resolved it and, while
#   it is unrated, asks its person at once (support.rating_requested); the
#   person rates it once, for good -- 1..5 and a comment kept as written.
#   The operator reads the rating in the row and the card, filters by it,
#   and reads the statistics of a period (support_stats).
#
# WHY TWO KINDS OF THREAD ID CHECK. Both sides take comms thread ids from
# the wire, and comms trusts whatever actor and thread we send it, so the
# check is ours, against the pointer table, BEFORE comms is called: the
# person's routes name no thread at all (their threads are read from the
# pointer table); the operator's routes accept only threads this product
# created for support. A guessed or foreign id is a 404 -- never a 403,
# which would confirm the id names a real conversation.
#
# THE SECTION ID IS RESOLVED, NEVER STORED: comms' create-or-find section
# endpoint is called for the key below and the answer is cached in
# process memory only. A reinstalled comms hands out a different id, and a
# persisted copy would point at nothing. No lock guards the cache: the
# endpoint is create-or-find, so two concurrent first callers get the
# same row.
#
# Two mechanisms beside it: the translation queue (translation.py, H39),
# which works on any support thread, and the spam bin (purge.py).
# =============================================================================

import base64
import binascii
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.comms import (
    CommsRejectedError,
    CommsUnavailableError,
    comms_configured,
    comms_request,
)
from app.core.config import settings
from app.core.exceptions import (
    AivisError,
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from app.modules.support import translation
from app.modules.support.dependencies import SupportOperator
from app.modules.support.models import (
    CATEGORIES,
    STATUS_OPEN,
    STATUS_RESOLVED,
    STATUS_SPAM,
    TO_SUPPORT,
    TO_USER,
    TOPIC_OTHER,
    TOPICS,
    SupportOperatorMute,
    SupportSpamTombstone,
    SupportThread,
    SupportTicket,
)
from app.modules.users.models import User

logger = structlog.get_logger()

_SECTIONS_PATH = "/api/v1/sections"
_THREADS_PATH = "/api/v1/threads"

# -- Idempotency keys for the calls that create ---------------------------
# comms takes a required Idempotency-Key on POST /threads and on POST
# /threads/{id}/messages, and its unique index on the key is GLOBAL --
# across every product and every person on that comms. So every key this
# module sends is namespaced by product and by the person acting.
#
# EVERY KEY IS THE CLIENT'S. Only the client knows that two requests are
# one press of "send" retried after a timeout rather than two appeals with
# the same text; it generates the key when the person presses send and
# reuses it on every retry. One appeal is one key, and both of its calls
# are keyed by it: the ticket's thread ("aivis:ticket:") and its first
# message ("aivis:msg:") -- a repeated submit gets the same thread back
# from comms and the same message, and the unique comms_thread_id turns
# the replay into "the ticket exists". comms fingerprints method, path and
# the RAW BODY BYTES, so the create body is byte-identical on every repeat
# of one intent: the same keys in the same order, built from the same
# values.
#
# LENGTH: comms accepts 1..200 characters. The client part is capped at
# SUPPORT_CLIENT_KEY_MAX_LEN = 100 (support/schemas.py); the longest
# prefix, "aivis:ticket:" (13) + a UUID (36) + ":" (1), is 50, so the
# longest key is 150. Whoever changes a prefix re-does this sum.
_TICKET_KEY_PREFIX = "aivis:ticket:"
_MESSAGE_KEY_PREFIX = "aivis:msg:"


def _ticket_idempotency_key(user_id: UUID, client_key: str) -> str:
    """The client's key for one appeal's thread, namespaced by its author."""
    return f"{_TICKET_KEY_PREFIX}{user_id}:{client_key}"


def _message_idempotency_key(actor_id: UUID, client_key: str) -> str:
    """The client's key for one message, namespaced by who sends it."""
    return f"{_MESSAGE_KEY_PREFIX}{actor_id}:{client_key}"


# The comms section every support request lands in. English on purpose:
# the label is shown to whoever administers comms, never in this product.
_SUPPORT_SECTION_KEY = "support"
_SUPPORT_SECTION_LABEL = "Support"

# The comms group of every support operator -- the address of a signal
# meant for all of them (a ticket nobody took, a ticket back in the pool).
# Its members are the section roster's, written in the one place below
# (emit_support_membership). Mirrored, not imported, by migration 0061.
SUPPORT_OPERATORS_GROUP = "support_operators"

# In-process cache ONLY (see module header). Reset on every restart; the
# next call re-resolves it.
_support_section_id: UUID | None = None

# The rating filter's word for "nobody rated it" (list_tickets, H41).
RATING_NONE = "none"

# A person with more support threads than this is the trigger of the glued
# feed's KNOWN CEILING (client_support_messages).
FEED_THREADS_CEILING = 20


# ---------------------------------------------------------------------------
# comms answers are input too
# ---------------------------------------------------------------------------


def _uuid_from_payload(payload: Any, key: str, what: str) -> UUID:
    """Read a UUID out of a comms response, or refuse.

    comms' answer is an INPUT to this module and gets the same treatment
    as any other: a missing key or a value that is not a uuid must come
    out as a clean refusal, not as a KeyError or ValueError turning into
    a 500 on a request the user is watching.
    """
    value = payload.get(key) if isinstance(payload, dict) else None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        logger.error("comms_payload_malformed", what=what, key=key)
        raise CommsUnavailableError() from None


def _read_page(payload: Any) -> tuple[list[Any], str | None]:
    """A comms message page -> (items, next_cursor), or refuse.

    The feeds are RESHAPED (H39: every item is rendered by
    translation.py), so the page is read rather than forwarded, and a page
    of another shape is a malformed answer -- the same clean refusal as
    _uuid_from_payload, never a feed that silently says "no messages".
    """
    items = payload.get("items") if isinstance(payload, dict) else None
    cursor = payload.get("next_cursor") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not (cursor is None or isinstance(cursor, str)):
        logger.error("comms_payload_malformed", what="messages", key="items")
        raise CommsUnavailableError()
    return items, cursor


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------


async def get_support_section_id() -> UUID:
    """Resolve the comms section id for support, caching it in memory.

    The cache is written ONLY on success: a failed resolve must not
    poison the process into refusing forever after one bad minute.
    """
    global _support_section_id
    if _support_section_id is not None:
        return _support_section_id

    payload = await comms_request(
        "POST",
        _SECTIONS_PATH,
        json={
            "key": _SUPPORT_SECTION_KEY,
            "label": _SUPPORT_SECTION_LABEL,
        },
    )
    section_id = _uuid_from_payload(payload, "id", "section")
    _support_section_id = section_id
    return section_id


# ---------------------------------------------------------------------------
# Threads and tickets
# ---------------------------------------------------------------------------


async def own_support_threads(
    session: AsyncSession, *, user: User
) -> list[SupportThread]:
    """Every support thread of this person -- history and tickets -- oldest
    first."""
    return list(
        (
            await session.execute(
                select(SupportThread)
                .where(SupportThread.user_id == user.id)
                .order_by(SupportThread.created_at, SupportThread.id)
            )
        ).scalars()
    )


async def _ticket_by_thread(
    session: AsyncSession, comms_thread_id: UUID
) -> tuple[SupportThread | None, SupportTicket | None]:
    """The pointer of a comms thread and its ticket (None for a history)."""
    row = (
        await session.execute(
            select(SupportThread, SupportTicket)
            .outerjoin(
                SupportTicket,
                SupportTicket.support_thread_id == SupportThread.id,
            )
            .where(SupportThread.comms_thread_id == comms_thread_id)
        )
    ).first()
    if row is None:
        return None, None
    return row[0], row[1]


def ticket_out(pointer: SupportThread, ticket: SupportTicket) -> dict[str, Any]:
    """A ticket as this product describes it -- codes, never labels."""
    return {
        "id": str(pointer.comms_thread_id),
        "topic": ticket.topic,
        "category": ticket.category,
        "status": ticket.status,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "status_changed_at": ticket.status_changed_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# The person: the form and the conversation
# ---------------------------------------------------------------------------


async def create_ticket(
    session: AsyncSession,
    *,
    user: User,
    topic: str,
    body: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """One appeal through the support form: a new ticket and its first
    message -- a new one even when the person has an open ticket.

    ONE INTENT, ONE TICKET: see the key rules above. `topic` is a code of
    models.TOPICS (the schema refuses anything else); the category follows
    from it, in that one table.

    comms is called BEFORE the rows are written, and that order is the
    point: a pointer to a thread that may not exist is worse than none. A
    person comms does not know yet (their recipient sync lags) is told
    "not ready", never comms' wording about a missing recipient.
    """
    section_id = await get_support_section_id()
    try:
        payload = await comms_request(
            "POST",
            _THREADS_PATH,
            json={
                "client": str(user.id),
                "operator_kind": "section",
                "operator_value": str(section_id),
                "kind": "ticket",
            },
            idempotency_key=_ticket_idempotency_key(user.id, idempotency_key),
        )
    except CommsRejectedError as exc:
        if exc.error_class == "not_found":
            logger.warning("support_recipient_not_synced", user_id=str(user.id))
            raise CommsUnavailableError(
                message="Support is not ready for this account yet",
                code="comms_recipient_pending",
            ) from exc
        raise
    comms_thread_id = _uuid_from_payload(payload, "id", "thread")

    pointer, ticket = await _ticket_by_thread(session, comms_thread_id)
    if pointer is not None and pointer.user_id != user.id:
        # comms answered with a thread of somebody else: a defect of comms
        # or of the key rule, never a reason to hand the thread over.
        logger.error("support_ticket_thread_foreign", thread_id=str(comms_thread_id))
        raise CommsUnavailableError()
    if pointer is None:
        try:
            async with session.begin_nested():
                pointer = SupportThread(
                    user_id=user.id, comms_thread_id=comms_thread_id,
                )
                session.add(pointer)
                await session.flush()
                ticket = SupportTicket(
                    support_thread_id=pointer.id,
                    topic=topic,
                    category=TOPICS[topic].category,
                    status=STATUS_OPEN,
                    status_changed_at=datetime.now(UTC),
                    version=1,
                )
                session.add(ticket)
                await session.flush()
        except IntegrityError:
            # The same appeal, replayed concurrently under the same key:
            # comms answered both with one thread, the other insert won.
            pointer, ticket = await _ticket_by_thread(session, comms_thread_id)
            if pointer is None or ticket is None:
                raise
            logger.info(
                "support_ticket_insert_race_lost", thread_id=str(comms_thread_id),
            )
    if ticket is None:
        # comms answered a ticket create with a thread we hold as a
        # person's HISTORY. comms never does (a `ticket` create is a fresh
        # thread), so this is a defect, refused rather than written into.
        logger.error("support_ticket_thread_is_history", thread_id=str(comms_thread_id))
        raise CommsUnavailableError()
    logger.info(
        "support_ticket_opened",
        user_id=str(user.id),
        thread_id=str(comms_thread_id),
        topic=topic,
    )
    message = await _post_and_route(
        session,
        user=user,
        pointer=pointer,
        ticket=ticket,
        body=body,
        key=_message_idempotency_key(user.id, idempotency_key),
    )
    await session.refresh(ticket)
    return {"ticket": ticket_out(pointer, ticket), "message": message}


async def send_dialog_message(
    session: AsyncSession, *, user: User, body: str, idempotency_key: str
) -> dict[str, Any]:
    """A message the person writes in their conversation, not through the
    form (owner ruling, H40 item 2): it goes to their latest OPEN ticket;
    with none open, to their latest ticket (it returns to work); with no
    ticket at all -- only the pre-H40 history, or nothing -- it opens a
    ticket "other". "Latest" is by creation."""
    row = (
        await session.execute(
            select(SupportThread, SupportTicket)
            .join(SupportTicket, SupportTicket.support_thread_id == SupportThread.id)
            .where(SupportThread.user_id == user.id)
            .order_by(
                (SupportTicket.status == STATUS_OPEN).desc(),
                SupportTicket.created_at.desc(),
                SupportThread.id.desc(),
            )
            .limit(1)
        )
    ).first()
    if row is None:
        created = await create_ticket(
            session,
            user=user,
            topic=TOPIC_OTHER,
            body=body,
            idempotency_key=idempotency_key,
        )
        return created["message"]
    pointer, ticket = row
    return await _post_and_route(
        session,
        user=user,
        pointer=pointer,
        ticket=ticket,
        body=body,
        key=_message_idempotency_key(user.id, idempotency_key),
    )


async def _post_and_route(
    session: AsyncSession,
    *,
    user: User,
    pointer: SupportThread,
    ticket: SupportTicket,
    body: str,
    key: str,
) -> dict[str, Any]:
    """Post the person's message into the ticket's thread, as written, and
    do what a person's message does to a ticket -- the one place it is
    done, for the form and the conversation alike:

      the ticket is not spam -> back to OPEN (comms has reopened its
        thread itself), `version` bumped -- an operator's write in flight
        sees it and refuses; the message queued for translation into the
        support language (H39); the operator signal, routed by who took
        the ticket.
      the ticket is spam -> the message is in the thread and that is all:
        no status change, no translation job (no paid model call on spam;
        the operator feed's catch-up queues one if somebody opens it), no
        signal (owner ruling, H40 item 7).

    The decision is the UPDATE's own: a ticket turned spam a moment ago
    matches nothing, so the message is treated as spam's.
    """
    message = await comms_request(
        "POST",
        f"{_THREADS_PATH}/{pointer.comms_thread_id}/messages",
        json={"sender": str(user.id), "body": body},
        idempotency_key=key,
    )
    message_id = _message_id(message)
    if message_id is None:
        logger.warning(
            "support_message_without_id", thread_id=str(pointer.comms_thread_id),
        )
        return message
    reopened = (
        await session.execute(
            update(SupportTicket)
            .where(
                SupportTicket.support_thread_id == ticket.support_thread_id,
                SupportTicket.status != STATUS_SPAM,
            )
            .values(
                status=STATUS_OPEN,
                version=SupportTicket.version + 1,
                status_changed_at=case(
                    (SupportTicket.status != STATUS_OPEN, func.now()),
                    else_=SupportTicket.status_changed_at,
                ),
            )
            .returning(SupportTicket.claimed_by_user_id)
        )
    ).first()
    if reopened is None:
        return message
    await translation.enqueue(
        session,
        pointer=pointer,
        message_id=message_id,
        direction=TO_SUPPORT,
        locale=settings.support_language,
        text=body,
    )
    # KNOWN CEILING (a message without its operator signal):
    #   1. Mechanics: the message is written by the comms POST above,
    #      outside this transaction; the signal is an outbox row of this
    #      transaction. When comms accepted the POST and this transaction
    #      then fails to commit, the message is in the thread and no
    #      operator is told. The translation shares the window but has a
    #      catch-up (the operator feed queues a missing translation when it
    #      is read); the signal has no reader to catch it up from.
    #   2. Status: acknowledged by design.
    #   3. Task: none -- the window is the commit itself failing after a
    #      successful POST; nothing observed has hit it.
    #   4. Trigger: a person's message in comms with no outbox row keyed
    #      aivis:support-message:<its id> behind it.
    #   5. Fix form: mint the message's identity before the POST, send it
    #      to comms as the message's Idempotency-Key and write the outbox
    #      row under the same identity first -- the signal then exists
    #      whenever the message can.
    #   6. Rejected for now: that fix replaces the message key rule (the
    #      client's key is the message's identity, H23 P-112), and emitting
    #      before the POST without it has no message id to key the signal by.
    await _emit_message_received(
        session,
        user,
        thread_id=pointer.comms_thread_id,
        message_id=message_id,
        topic=ticket.topic,
        claimed_by=reopened[0],
    )
    return message


def _message_id(message: Any) -> UUID | None:
    value = message.get("id") if isinstance(message, dict) else None
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# The person's one conversation
# ---------------------------------------------------------------------------


def _message_key_of(row: Any) -> tuple[datetime, UUID] | None:
    """A message's place in the glued feed: (created_at, id), newest first
    -- comms' own order inside a thread."""
    if not isinstance(row, dict):
        return None
    try:
        when = datetime.fromisoformat(str(row.get("created_at")))
        mid = UUID(str(row.get("id")))
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        return None
    return when, mid


def _encode_feed_cursor(
    anchors: dict[UUID, str | None], boundary: tuple[datetime, UUID]
) -> str:
    raw = json.dumps(
        {
            "t": {str(k): v for k, v in anchors.items()},
            "a": boundary[0].isoformat(),
            "i": str(boundary[1]),
        },
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_feed_cursor(
    token: str,
) -> tuple[dict[UUID, str | None], tuple[datetime, UUID]]:
    try:
        doc = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        anchors = {UUID(k): v for k, v in doc["t"].items()}
        boundary = (datetime.fromisoformat(doc["a"]), UUID(doc["i"]))
    except (binascii.Error, ValueError, KeyError, TypeError, AttributeError):
        raise BadRequestError(
            "Malformed cursor", code="support_cursor_malformed",
        ) from None
    if boundary[0].tzinfo is None or not all(
        v is None or isinstance(v, str) for v in anchors.values()
    ):
        raise BadRequestError("Malformed cursor", code="support_cursor_malformed")
    return anchors, boundary


async def _thread_page(
    thread_id: UUID,
    *,
    anchor: str | None,
    limit: int,
    user_locale: str | None,
) -> tuple[list[Any], str | None]:
    params: dict[str, Any] = {"limit": limit}
    if user_locale is not None:
        params["locale"] = user_locale
    if anchor is not None:
        params["cursor"] = anchor
    return _read_page(
        await comms_request(
            "GET", f"{_THREADS_PATH}/{thread_id}/messages", params=params,
        )
    )


async def client_support_messages(
    session: AsyncSession,
    *,
    user: User,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    """The person's support conversation, as they read it: all their
    support threads glued into one feed, newest first (H40 item 2).

    Each message is rendered by translation.client_feed, thread by thread
    -- the catch-up of a reply whose translation was lost included (it
    needs its thread's pointer) -- and put in its place by (created_at,
    id). No operator's name rides out: a reply carries its sender id, and
    the screen signs every message not the person's own "Support".

    THE CURSOR IS OURS: where each thread stands (comms' own cursor, or
    null for its top) and the place of the last message given out (the
    boundary). A page reads one comms page per thread, keeps what is older
    than the boundary, takes the newest `limit` of all of them, and moves
    each thread to just after its last message taken -- a thread taken
    from only in part is re-read up to that message to get comms' cursor
    there (one more call). Messages never move, so this is exact; a thread
    born after the first page has only newer messages and is not in the
    cursor. velo's mechanism (its client_support_messages), carried over.

    # KNOWN CEILING (the glued feed reads every thread of the person):
    #   1. Mechanics: one comms call per support thread per page, plus one
    #      per thread taken from in part, and a cursor that grows with the
    #      thread count -- a ticket per appeal makes the count grow with
    #      the person's history.
    #   2. Status: acknowledged by design.
    #   3. Task: none -- the trigger says when it is needed.
    #   4. Trigger: support_feed_threads_many in the app log (a person with
    #      more than FEED_THREADS_CEILING support threads opened the feed).
    #   5. Fix form: read only the threads whose activity reaches into the
    #      page -- their last_message_at, from comms' client list
    #      (INTEGRATION.md section 13) -- and drop the rest from the cursor.
    #   6. Rejected: gluing only the latest K threads -- it hides the
    #      person's own history from them.
    """
    threads = await own_support_threads(session, user=user)
    by_id = {t.comms_thread_id: t for t in threads}
    if len(by_id) > FEED_THREADS_CEILING:
        logger.warning("support_feed_threads_many", threads=len(by_id))
    boundary: tuple[datetime, UUID] | None = None
    if cursor is None:
        anchors: dict[UUID, str | None] = dict.fromkeys(by_id)
    else:
        anchors, boundary = _decode_feed_cursor(cursor)
        anchors = {tid: a for tid, a in anchors.items() if tid in by_id}
    user_locale = translation.reply_language(user)

    # What each thread offers below the boundary: (the anchor its page was
    # read from, that page as comms gave it, its keyed rows below the
    # boundary, comms' next cursor).
    offers: dict[
        UUID, tuple[str | None, list[Any], list[tuple[Any, dict]], str | None]
    ] = {}
    for tid, anchor in anchors.items():
        while True:
            items, next_cursor = await _thread_page(
                tid, anchor=anchor, limit=limit, user_locale=user_locale,
            )
            below = [
                (k, row)
                for row in items
                if (k := _message_key_of(row)) is not None
                and (boundary is None or k < boundary)
            ]
            if below or next_cursor is None:
                break
            anchor = next_cursor  # a whole page newer than the boundary
        offers[tid] = (anchor, items, below, next_cursor)

    candidates = sorted(
        ((k, tid, row) for tid, (_, _, below, _) in offers.items() for k, row in below),
        key=lambda c: c[0],
        reverse=True,
    )[:limit]
    taken: dict[UUID, list[dict]] = {}
    for _, tid, row in candidates:
        taken.setdefault(tid, []).append(row)

    new_anchors: dict[UUID, str | None] = {}
    for tid, (anchor, items, below, next_cursor) in offers.items():
        mine = taken.get(tid, [])
        if len(mine) == len(below):
            if next_cursor is not None:
                new_anchors[tid] = next_cursor
            continue  # read to its end
        if not mine:
            new_anchors[tid] = anchor
            continue
        # Taken in part: re-read the same page up to the last message taken
        # and stand on comms' cursor there.
        last = next(i for i, row in enumerate(items) if row is mine[-1])
        _, reanchored = await _thread_page(
            tid, anchor=anchor, limit=last + 1, user_locale=user_locale,
        )
        new_anchors[tid] = reanchored

    # One thread after another, in a fixed order: the catch-up inserts, and
    # two readers of the same conversation must take the unique index in
    # one order (translation.catch_up says why).
    rendered: dict[UUID, list[dict]] = {}
    for tid in sorted(taken, key=str):
        rendered[tid] = await translation.client_feed(
            session,
            pointer=by_id[tid],
            user_locale=user_locale,
            messages=taken[tid],
        )
    position = dict.fromkeys(rendered, 0)
    items_out: list[dict] = []
    for _, tid, _ in candidates:
        items_out.append(rendered[tid][position[tid]])
        position[tid] += 1

    next_page = None
    if candidates and new_anchors:
        next_page = _encode_feed_cursor(new_anchors, candidates[-1][0])
    return {"items": items_out, "next_cursor": next_page}


async def mark_support_read(session: AsyncSession, *, user: User) -> dict[str, Any]:
    """Read up to now in every support thread of the person: one call per
    thread (comms keeps a read pointer per thread). Returns what is left
    unread in all of them -- 0 unless a message arrived meanwhile.

    `last_read_at` is not taken from the wire: comms stamps now."""
    unread = 0
    for pointer in await own_support_threads(session, user=user):
        answer = await comms_request(
            "POST",
            f"{_THREADS_PATH}/{pointer.comms_thread_id}/read",
            json={"participant": str(user.id)},
        )
        if isinstance(answer, dict) and isinstance(answer.get("unread"), int):
            unread += answer["unread"]
    return {"unread": unread}


async def support_unread(session: AsyncSession, *, user: User) -> dict[str, Any]:
    """What the person has not read in all their support threads -- one
    batch call to comms, summed (H40 item 10). No thread at all is 0
    without asking comms."""
    threads = await own_support_threads(session, user=user)
    if not threads:
        return {"unread": 0}
    answer = await comms_request(
        "POST",
        f"{_THREADS_PATH}/unread-counts",
        json={
            "participant": str(user.id),
            "thread_ids": [str(t.comms_thread_id) for t in threads],
        },
    )
    counts = answer.get("counts") if isinstance(answer, dict) else None
    if not isinstance(counts, dict):
        logger.error("comms_payload_malformed", what="unread-counts", key="counts")
        raise CommsUnavailableError()
    return {"unread": sum(n for n in counts.values() if isinstance(n, int))}


# ---------------------------------------------------------------------------
# The operator side
# ---------------------------------------------------------------------------
#
# WHO OPERATES, AND WHAT THEY SEE: every active staff member is a support
# operator (dependencies.py), and every operator sees every ticket -- the
# list is OUR table, filtered by our columns, and comms is not asked who
# may see what (owner ruling, H40 gate).
#
# WRITING IS comms' TO GATE: comms' can_post_message admits the thread's
# client or its ASSIGNEE and nobody else, so only the operator who took a
# ticket replies; comms answers anyone else 403, forwarded as a 409 that
# says what to do (reply_to_support_thread). claim / assign / release /
# status are admitted by comms for every operator who serves the section
# -- every active staff member, by the roster below.
#
# THE ORDER OF EVERY OPERATOR WRITE: the ticket is read, comms is told,
# then the ticket is written by compare-and-set -- on its version for a
# status, on its taker for a handover. Nothing is locked across the comms
# call: an HTTP call inside a row lock would block the person's message
# for as long as comms takes.


def _person(user: User | None) -> dict[str, Any] | None:
    """Who a person is, for an operator: the pieces, not a string -- the
    staff area joins first and last name in the view (StaffUsersView);
    `email` is None for a Telegram-only account. Nothing is masked: an
    operator is answering this person and needs to know who they are."""
    if user is None:
        return None
    profile = user.profile or {}
    return {
        "user_id": str(user.id),
        "first_name": profile.get("first_name") or None,
        "last_name": profile.get("last_name") or None,
        "email": user.email,
    }


async def _ticket_rows(
    session: AsyncSession, rows: list[Any]
) -> list[dict[str, Any]]:
    """Tickets as an operator reads them -- THE row of the list and of the
    card (a signal opens the card without the list): the ticket's codes
    and dates, who opened it, who took it, and the person's history
    thread. `rows` are (SupportTicket, SupportThread) pairs; one query per
    kind of fact, whatever their number."""
    people = {p.user_id for _, p in rows} | {
        uid
        for t, _ in rows
        for uid in (
            t.claimed_by_user_id,
            t.resolved_by_user_id,
            t.rated_resolver_user_id,
        )
        if uid is not None
    }
    users: dict[UUID, User] = {}
    if people:
        users = {
            u.id: u
            for u in (
                await session.execute(select(User).where(User.id.in_(people)))
            ).scalars()
        }
    history: dict[UUID, UUID] = {}
    openers = {p.user_id for _, p in rows}
    if openers:
        history = {
            client: thread_id
            for client, thread_id in (
                await session.execute(
                    select(SupportThread.user_id, SupportThread.comms_thread_id)
                    .outerjoin(
                        SupportTicket,
                        SupportTicket.support_thread_id == SupportThread.id,
                    )
                    .where(
                        SupportThread.user_id.in_(openers),
                        SupportTicket.support_thread_id.is_(None),
                    )
                )
            ).all()
        }
    return [
        {
            **ticket_out(pointer, ticket),
            "opener": _person(users.get(pointer.user_id)),
            "claimed_by": (
                _person(users.get(ticket.claimed_by_user_id))
                if ticket.claimed_by_user_id is not None
                else None
            ),
            "history_thread_id": (
                str(history[pointer.user_id]) if pointer.user_id in history else None
            ),
            # H41: the operator who last resolved it, and the person's
            # rating with whom it rated.
            "resolved_by": _person_or_none(users, ticket.resolved_by_user_id),
            "rating": _rating_out(ticket, users),
        }
        for ticket, pointer in rows
    ]


def _person_or_none(users: dict[UUID, User], user_id: UUID | None) -> dict | None:
    return _person(users.get(user_id)) if user_id is not None else None


def _rating_out(ticket: SupportTicket, users: dict[UUID, User]) -> dict | None:
    """The person's rating as an operator reads it: the stars, the comment
    AS WRITTEN (never translated, owner ruling), `comment_locale` -- the
    person's INTERFACE language when they rated, which a screen shows as
    the likely language of the text (nothing detects it) -- when, and the
    operator it is about."""
    if ticket.rating is None:
        return None
    return {
        "stars": ticket.rating,
        "comment": ticket.rating_comment,
        "comment_locale": ticket.rating_locale,
        "rated_at": ticket.rated_at.isoformat() if ticket.rated_at else None,
        "rated_resolver": _person_or_none(users, ticket.rated_resolver_user_id),
    }


def _encode_list_cursor(created_at: datetime, thread_row_id: UUID) -> str:
    raw = json.dumps(
        {"a": created_at.isoformat(), "i": str(thread_row_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_list_cursor(token: str) -> tuple[datetime, UUID]:
    try:
        doc = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        when = datetime.fromisoformat(doc["a"])
        row_id = UUID(doc["i"])
    except (binascii.Error, ValueError, KeyError, TypeError, AttributeError):
        raise BadRequestError(
            "Malformed cursor", code="support_cursor_malformed",
        ) from None
    if when.tzinfo is None:
        raise BadRequestError("Malformed cursor", code="support_cursor_malformed")
    return when, row_id


async def list_tickets(
    session: AsyncSession,
    *,
    categories: set[str] | None,
    status: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
    limit: int,
    cursor: str | None,
    ratings: set[str] | None = None,
) -> dict[str, Any]:
    """Tickets, newest appeal first (H40 item 3) -- from our own table.

    `categories` is "any of these"; none -- every category. `ratings`
    likewise (H41): stars "1".."5", and RATING_NONE for a ticket nobody
    rated; none -- any rating or none. Without
    `status` the list is every ticket but SPAM (spam leaves the common
    list); `status=spam` is the spam tab. `created_from` is inclusive,
    `created_to` exclusive -- the operator's day, its edges in the
    operator's own time zone, computed by the screen.

    comms is not asked anything. A row carries no last message: comms
    reads one thread's feed per call, and the list does not pay N+1 for a
    preview.
    """
    stmt = (
        select(SupportTicket, SupportThread)
        .join(SupportThread, SupportThread.id == SupportTicket.support_thread_id)
        .order_by(
            SupportTicket.created_at.desc(),
            SupportTicket.support_thread_id.desc(),
        )
        .limit(limit + 1)
    )
    if status is not None:
        stmt = stmt.where(SupportTicket.status == status)
    else:
        stmt = stmt.where(SupportTicket.status != STATUS_SPAM)
    if categories:
        stmt = stmt.where(SupportTicket.category.in_(sorted(categories)))
    if ratings:
        stars = sorted(int(r) for r in ratings if r != RATING_NONE)
        any_of = [SupportTicket.rating.in_(stars)] if stars else []
        if RATING_NONE in ratings:
            any_of.append(SupportTicket.rating.is_(None))
        stmt = stmt.where(or_(*any_of))
    if created_from is not None:
        stmt = stmt.where(SupportTicket.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(SupportTicket.created_at < created_to)
    if cursor is not None:
        when, row_id = _decode_list_cursor(cursor)
        stmt = stmt.where(
            (SupportTicket.created_at < when)
            | (
                (SupportTicket.created_at == when)
                & (SupportTicket.support_thread_id < row_id)
            )
        )
    rows = list((await session.execute(stmt)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more:
        last = rows[-1][0]
        next_cursor = _encode_list_cursor(last.created_at, last.support_thread_id)
    return {"items": await _ticket_rows(session, rows), "next_cursor": next_cursor}


async def get_ticket(session: AsyncSession, *, thread_id: UUID) -> dict[str, Any]:
    """One ticket by its thread id, as the list shows it: the card an
    operator opens from a signal, which carries only the thread id. Any
    status, spam included.

    404 for anything that is not a ticket: a person's history (it has no
    card), a thread of anything else, an id nobody has. One answer for
    all: existence does not leak.
    """
    row = (
        await session.execute(
            select(SupportTicket, SupportThread)
            .join(SupportThread, SupportThread.id == SupportTicket.support_thread_id)
            .where(SupportThread.comms_thread_id == thread_id)
        )
    ).first()
    if row is None:
        raise NotFoundError("Ticket not found", code="support_ticket_not_found")
    (ticket,) = await _ticket_rows(session, [row])
    return ticket


async def _require_support_thread(
    session: AsyncSession, thread_id: UUID
) -> tuple[SupportThread, SupportTicket | None]:
    """A comms thread id from the wire -> a KNOWN support thread and its
    ticket (None for a person's history), or 404 before comms is asked.
    Rows land in support_threads only through create_ticket (and the
    pre-H40 conversations), so a row is proof the id names a support
    conversation this product created."""
    pointer, ticket = await _ticket_by_thread(session, thread_id)
    if pointer is None:
        raise NotFoundError("Support thread not found")
    return pointer, ticket


async def _require_ticket(
    session: AsyncSession, thread_id: UUID
) -> tuple[SupportThread, SupportTicket]:
    """A support thread that is a TICKET. A person's history is read-only
    (owner ruling): no claim, no reply, no status -- 409."""
    pointer, ticket = await _require_support_thread(session, thread_id)
    if ticket is None:
        raise ConflictError(
            "A support history thread is read-only",
            code="support_history_read_only",
        )
    return pointer, ticket


async def get_operator_thread_messages(
    session: AsyncSession,
    *,
    thread_id: UUID,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    """One support thread -- a ticket or a person's history -- newest
    messages first, for an operator.

    NO ACTOR IS SENT, and none is taken: comms' feed scopes nothing, so
    the gate is the whole gate -- the operator dependency on the route
    plus the pointer check here.

    H39: read in the support language -- and the SAME page again in the
    person's language when it differs: only that read says what became of
    a staff reply for the person (translation.staff_feed, which also
    queues what nobody asked for yet -- hence the write session). The feed
    pages exactly alike with any locale.
    """
    pointer, _ = await _require_support_thread(session, thread_id)
    client = await session.get(User, pointer.user_id)
    user_locale = translation.reply_language(client) if client is not None else None

    async def _page(locale: str) -> tuple[list[Any], str | None]:
        params: dict[str, Any] = {"limit": limit, "locale": locale}
        if cursor is not None:
            params["cursor"] = cursor
        return _read_page(
            await comms_request(
                "GET", f"{_THREADS_PATH}/{thread_id}/messages", params=params
            )
        )

    messages, next_cursor = await _page(settings.support_language)
    user_items: list[Any] = []
    if user_locale is not None:
        user_items, _ = await _page(user_locale)
    return {
        "items": await translation.staff_feed(
            session,
            pointer=pointer,
            messages=messages,
            user_locale=user_locale,
            user_items=user_items,
        ),
        "next_cursor": next_cursor,
    }


async def retry_support_translation(
    session: AsyncSession, *, thread_id: UUID, message_id: UUID
) -> dict[str, Any]:
    """Ask again for a message whose translation's job failed (H39). Any
    operator: nothing is posted as anyone. 409 when there is nothing to
    retry; 404 when the message is out of the thread's reach."""
    pointer, _ = await _require_support_thread(session, thread_id)
    return await translation.retry(session, pointer=pointer, message_id=message_id)


async def claim_support_ticket(
    session: AsyncSession, *, operator: SupportOperator, thread_id: UUID
) -> dict[str, Any]:
    """Take a ticket -- the act that grants the right to reply and routes
    the person's messages to this operator alone.

    comms ARBITRATES: it claims idempotently by outcome (the holder
    claiming again is a success), and a ticket held by somebody else is
    its 409, forwarded in our words. The taker is written here only after
    comms said yes. If this transaction is then lost, comms has an
    assignee and the ticket has none: the person's messages go to every
    operator until the taker claims again -- comms answers yes again, and
    this writes it.
    """
    _, ticket = await _require_ticket(session, thread_id)
    try:
        payload = await comms_request(
            "POST",
            f"{_THREADS_PATH}/{thread_id}/claim",
            json={"operator": str(operator.id)},
        )
    except CommsRejectedError as exc:
        if exc.error_class == "conflict":
            raise ConflictError(
                "This request has already been taken by another operator",
                code="support_thread_already_claimed",
            ) from exc
        raise
    if not isinstance(payload, dict) or payload.get("claimed") is not True:
        logger.error("comms_payload_malformed", what="claim", key="claimed")
        raise CommsUnavailableError()
    if ticket.claimed_by_user_id != operator.id:
        await session.execute(
            update(SupportTicket)
            .where(SupportTicket.support_thread_id == ticket.support_thread_id)
            .values(claimed_by_user_id=operator.id, version=SupportTicket.version + 1)
        )
    logger.info(
        "support_ticket_claimed",
        thread_id=str(thread_id),
        operator_id=str(operator.id),
    )
    return await get_ticket(session, thread_id=thread_id)


async def _require_operator_user(session: AsyncSession, user_id: UUID) -> User:
    """The person a ticket is handed to: an ACTIVE support operator, or a
    422 before comms is called (comms would refuse one off its roster with
    a 422 of its own, in its wording)."""
    from app.modules.staff.models import StaffProfile

    row = (
        await session.execute(
            select(User)
            .join(StaffProfile, StaffProfile.user_id == User.id)
            .where(User.id == user_id, StaffProfile.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if row is None:
        raise AivisError(
            message="The assignee must be an active support operator",
            code="support_assignee_not_operator",
            status_code=422,
        )
    return row


async def _record_taker(
    session: AsyncSession,
    ticket: SupportTicket,
    *,
    seen: UUID | None,
    taker: UUID | None,
) -> int:
    """Write the taker comms has just set, if the ticket still has the one
    read before the call; bump the version (a status change read before
    the handover is then refused). Lost -> 409 and the drift log -- the
    KNOWN CEILING on assign_ticket."""
    changed = (
        await session.execute(
            update(SupportTicket)
            .where(
                SupportTicket.support_thread_id == ticket.support_thread_id,
                SupportTicket.claimed_by_user_id.is_not_distinct_from(seen),
            )
            .values(claimed_by_user_id=taker, version=SupportTicket.version + 1)
            .returning(SupportTicket.version)
        )
    ).first()
    if changed is None:
        logger.warning(
            "support_handover_drift", thread_id=str(ticket.support_thread_id),
        )
        raise ConflictError(
            "The ticket changed hands meanwhile -- read it again",
            code="support_ticket_changed",
        )
    return int(changed[0])


async def _handover(
    *, operator: SupportOperator, thread_id: UUID, verb: str, body: dict[str, Any]
) -> None:
    """comms' assign / release, its refusals in our words: a crossing call
    (409 conflict) is "read it again"; anything else as comms answered."""
    try:
        await comms_request(
            "POST",
            f"{_THREADS_PATH}/{thread_id}/{verb}",
            json={"operator": str(operator.id), **body},
        )
    except CommsRejectedError as exc:
        if exc.error_class == "conflict":
            raise ConflictError(
                "The ticket changed hands meanwhile -- read it again",
                code="support_ticket_changed",
            ) from exc
        raise


async def assign_ticket(
    session: AsyncSession,
    *,
    operator: SupportOperator,
    thread_id: UUID,
    assignee_id: UUID,
) -> dict[str, Any]:
    """Hand a ticket to another operator (H40 item 5): comms' `assign`,
    then the taker here. Any operator may hand over (comms admits the
    roster, and every active staff member is on it); the assignee must be
    an active operator -- 422 before comms otherwise. The new taker writes,
    the previous one no longer can, and the person's messages now signal
    the new taker alone. comms tells nobody (INTEGRATION.md section 14), so
    we tell the assignee (support.ticket_assigned).

    The same operator again: comms is asked again -- idempotent by
    outcome, and it aligns comms if the two ever disagreed -- and nothing
    else happens: no write, no signal.

    # KNOWN CEILING (two handovers of one ticket in quick succession can be
    # recorded out of order):
    #   1. Mechanics: comms is called first, the taker written here after.
    #      Two handovers comms performs one after the other (A, then B) can
    #      reach this write in the other order: the write is a
    #      compare-and-set on the taker read before the comms call, so the
    #      later write loses -- but "later" here is not comms' order. comms
    #      may then hold B while the ticket says A, and the person's
    #      messages signal A until the next handover.
    #   2. Status: acknowledged by design.
    #   3. Task: none -- comms has no revision number on a thread to order
    #      its answers by (the fix below waits for one).
    #   4. Trigger: support_handover_drift in the app log (this write lost
    #      its compare-and-set: the taker changed while comms was called).
    #   5. Fix form: comms' thread revision in every answer that carries a
    #      thread; record a taker only from an answer whose revision is
    #      greater than the one recorded.
    #   6. Rejected: holding the ticket's row lock across the comms call --
    #      an HTTP call inside a lock blocks the person's messages for as
    #      long as comms takes.
    """
    pointer, ticket = await _require_ticket(session, thread_id)
    target = await _require_operator_user(session, assignee_id)
    seen = ticket.claimed_by_user_id
    await _handover(
        operator=operator,
        thread_id=thread_id,
        verb="assign",
        body={"assignee": str(assignee_id)},
    )
    if seen != assignee_id:
        version = await _record_taker(session, ticket, seen=seen, taker=assignee_id)
        await _emit_handover(
            session,
            type=ASSIGNED_TYPE,
            pointer=pointer,
            ticket=ticket,
            actor=operator.user,
            version=version,
            target=("user", str(target.id)),
        )
    return await get_ticket(session, thread_id=thread_id)


async def release_ticket(
    session: AsyncSession, *, operator: SupportOperator, thread_id: UUID
) -> dict[str, Any]:
    """Return a ticket to the pool (H40 item 5): comms' `release`, then no
    taker here -- the person's messages signal every operator again. comms
    calls nobody on a release, so we tell every operator
    (support.ticket_released). Already in the pool: comms is asked again
    (idempotent) and nothing else happens. Same ordering ceiling as
    assign_ticket."""
    pointer, ticket = await _require_ticket(session, thread_id)
    seen = ticket.claimed_by_user_id
    await _handover(operator=operator, thread_id=thread_id, verb="release", body={})
    if seen is not None:
        version = await _record_taker(session, ticket, seen=seen, taker=None)
        await _emit_handover(
            session,
            type=RELEASED_TYPE,
            pointer=pointer,
            ticket=ticket,
            actor=operator.user,
            version=version,
            target=("group", SUPPORT_OPERATORS_GROUP),
        )
    return await get_ticket(session, thread_id=thread_id)


async def _set_thread_status(
    *, operator: SupportOperator, thread_id: UUID, status: str
) -> None:
    await comms_request(
        "POST",
        f"{_THREADS_PATH}/{thread_id}/status",
        json={"operator": str(operator.id), "status": status},
    )


async def set_ticket_status(
    session: AsyncSession,
    *,
    operator: SupportOperator,
    thread_id: UUID,
    status: str,
) -> dict[str, Any]:
    """Move an OPEN ticket to resolved / rejected / duplicate / spam (H40
    item 4), and its thread to comms' `resolved` -- never `closed`. Any
    operator, claimed or not (comms admits the roster).

    THE ORDER: the ticket is read (its version), comms is told, then the
    ticket is written by compare-and-set on (OPEN, version). A second
    operator's change, a handover or a message of the person in between
    bumps the version: this change is refused (409) and the ticket stays
    as they left it.

    # KNOWN CEILING (comms' thread status may disagree with the ticket's):
    #   1. Mechanics: comms is told before the ticket is written. When the
    #      person's message lands between the two -- comms reopens the
    #      thread, then this call resolves it -- the compare-and-set fails
    #      and the ticket is OPEN while comms says `resolved`. And a
    #      person's message into a SPAM ticket: comms reopens the thread,
    #      the ticket stays spam (owner ruling) -- comms says `open`.
    #   2. Status: acknowledged by design.
    #   3. Task: none -- the ticket's status is the truth every screen and
    #      signal reads; comms' status changes nothing for the person while
    #      comms' auto-close is off (THREAD_AUTO_CLOSE_DAYS=0, the
    #      installer) and does not stop anyone writing.
    #   4. Trigger: support_ticket_status_drift in the app log (a status
    #      change refused after comms was told); and comms' auto-close
    #      turned back on on a box -- a mismatch would then close threads
    #      on comms' own schedule, with a notice to the person.
    #   5. Fix form: after a refused change, read the ticket again and set
    #      comms' thread to the status the ticket says (`open` or
    #      `resolved`) -- comms 3.11 allows both moves by an operator.
    #   6. Rejected: holding the ticket row locked across the comms call --
    #      an HTTP call inside a lock blocks the person's message for as
    #      long as comms takes.
    """
    pointer, ticket = await _require_ticket(session, thread_id)
    if ticket.status != STATUS_OPEN:
        raise ConflictError(
            "Only an open ticket changes its status",
            code="support_ticket_not_open",
        )
    seen = ticket.version
    await _set_thread_status(operator=operator, thread_id=thread_id, status="resolved")
    changed = (
        await session.execute(
            update(SupportTicket)
            .where(
                SupportTicket.support_thread_id == ticket.support_thread_id,
                SupportTicket.status == STATUS_OPEN,
                SupportTicket.version == seen,
            )
            .values(
                status=status,
                status_changed_at=func.now(),
                version=SupportTicket.version + 1,
                # H41: who resolved it -- the last to do so. Any other
                # close leaves the last resolver standing.
                resolved_by_user_id=(
                    operator.id
                    if status == STATUS_RESOLVED
                    else SupportTicket.resolved_by_user_id
                ),
            )
            .returning(SupportTicket.version, SupportTicket.rating)
        )
    ).first()
    if changed is None:
        logger.warning("support_ticket_status_drift", thread_id=str(thread_id))
        raise ConflictError(
            "The ticket changed meanwhile -- read it again",
            code="support_ticket_changed",
        )
    version, rating = changed
    if status == STATUS_RESOLVED and rating is None:
        await _emit_rating_request(session, pointer=pointer, version=version)
    logger.info("support_ticket_status", thread_id=str(thread_id), status=status)
    return await get_ticket(session, thread_id=thread_id)


async def reopen_ticket(
    session: AsyncSession, *, operator: SupportOperator, thread_id: UUID
) -> dict[str, Any]:
    """Back to OPEN by an operator (H40 item 6): "back to work" from
    resolved / rejected / duplicate, "not spam" from spam -- while the
    spam is younger than the retention (SUPPORT_SPAM_RETENTION_DAYS);
    older is a 409, and once the bin has emptied it the ticket is gone
    (404). comms' thread goes back to `open` (a manual move since 3.11).

    The same compare-and-set as a status change: the status and version
    read before the comms call, and for spam its age, all still true at
    the write -- otherwise 409. The bin takes a ticket under its row lock
    by the same age rule, so of "not spam" and the bin exactly one gets it.
    """
    _, ticket = await _require_ticket(session, thread_id)
    if ticket.status == STATUS_OPEN:
        raise ConflictError("The ticket is open already", code="support_ticket_open")
    cutoff = datetime.now(UTC) - timedelta(days=settings.support_spam_retention_days)
    if ticket.status == STATUS_SPAM and ticket.status_changed_at <= cutoff:
        raise ConflictError(
            "Spam older than the retention cannot come back",
            code="support_spam_expired",
        )
    seen_status, seen_version = ticket.status, ticket.version
    await _set_thread_status(operator=operator, thread_id=thread_id, status="open")
    conditions = [
        SupportTicket.support_thread_id == ticket.support_thread_id,
        SupportTicket.status == seen_status,
        SupportTicket.version == seen_version,
    ]
    if seen_status == STATUS_SPAM:
        conditions.append(SupportTicket.status_changed_at > cutoff)
    changed = (
        await session.execute(
            update(SupportTicket)
            .where(*conditions)
            .values(
                status=STATUS_OPEN,
                status_changed_at=func.now(),
                version=SupportTicket.version + 1,
            )
            .returning(SupportTicket.version)
        )
    ).first()
    if changed is None:
        still, _ = await _ticket_by_thread(session, thread_id)
        if still is None:
            # The bin took it between the read and the write.
            raise NotFoundError("Ticket not found", code="support_ticket_not_found")
        logger.warning("support_ticket_status_drift", thread_id=str(thread_id))
        raise ConflictError(
            "The ticket changed meanwhile -- read it again",
            code="support_ticket_changed",
        )
    logger.info("support_ticket_reopened", thread_id=str(thread_id))
    return await get_ticket(session, thread_id=thread_id)


async def reply_to_support_thread(
    session: AsyncSession,
    *,
    operator: SupportOperator,
    thread_id: UUID,
    body: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Answer as this operator -- into a ticket; a person's history is
    read-only (409).

    WRITE-AUTHZ IS NOT OURS TO GRANT: comms' can_post_message admits the
    thread's client or its ASSIGNEE and nobody else, so an operator who
    has not taken the ticket is refused by comms with a 403, forwarded
    here (forward_403) and turned into a 409 that says what to do: claim
    first. 409 rather than 403 because the role is fine -- the state is
    wrong.

    A reply in a ticket of any status is allowed (comms' write-authz does
    not look at the status) and moves nothing: comms revives a thread only
    for a message from the CLIENT.

    H39: when the person reads another language than support's, the
    reply's translation into theirs is queued in this transaction.
    """
    pointer, _ = await _require_ticket(session, thread_id)
    try:
        message = await comms_request(
            "POST",
            f"{_THREADS_PATH}/{thread_id}/messages",
            json={"sender": str(operator.id), "body": body},
            forward_403=True,
            idempotency_key=_message_idempotency_key(operator.id, idempotency_key),
        )
    except CommsRejectedError as exc:
        if exc.error_class == "forbidden":
            raise ConflictError(
                "Claim this request before replying to it",
                code="support_thread_not_claimed",
            ) from exc
        raise

    client = await session.get(User, pointer.user_id)
    target = translation.reply_language(client) if client is not None else None
    if target is not None:
        await translation.enqueue_for_sent(
            session,
            pointer=pointer,
            message=message,
            direction=TO_USER,
            locale=target,
            text=body,
        )
    return message


async def list_support_operators(session: AsyncSession) -> dict[str, Any]:
    """Every active support operator, for "hand over to" (H40 item 5) --
    the same set comms' roster holds (emit_support_membership)."""
    from app.modules.staff.models import StaffProfile

    users = (
        await session.execute(
            select(User)
            .join(StaffProfile, StaffProfile.user_id == User.id)
            .where(StaffProfile.is_active.is_(True))
            .order_by(User.created_at, User.id)
        )
    ).scalars()
    return {"items": [_person(u) for u in users], "next_cursor": None}


# ---------------------------------------------------------------------------
# The rating (H41)
# ---------------------------------------------------------------------------
#
# When an operator RESOLVES a ticket nobody rated yet, its person is asked
# at once -- "How did we do?" -- and rates it once, for good: 1..5 stars
# and, if they like, a comment kept as written (owner ruling). A ticket
# back at work and resolved again asks again while it is unrated; a rated
# ticket never asks again, and its rating stays with the operator it rated.

RATING_REQUEST_TYPE = "support.rating_requested"
OPEN_RATING_ACTION = "open_support_rating"

# In-app text in the person's language: ru for a person who reads Russian,
# en for everyone else (owner ruling, as support.translation_unavailable).
_RATING_REQUEST_TEXT = {
    "ru": (
        "Как мы помогли?",
        "Ваше обращение в поддержку решено. Оцените нашу помощь: это займёт "
        "пару секунд.",
    ),
    "en": (
        "How did we do?",
        "Your support request is resolved. Please rate our help: it takes a "
        "couple of seconds.",
    ),
}


async def _emit_rating_request(
    session: AsyncSession, *, pointer: SupportThread, version: int
) -> None:
    """Ask the person to rate the ticket just RESOLVED, in the transaction
    that resolves it. The person's own delivery hours are kept (the type
    declares no `recipient_schedule`, comms' default `respect`).

    One request per move to RESOLVED: the key names the ticket's version
    after that move, so a repeat of the same document is one notification
    and a later RESOLVED (after back to work) is a new one. The action
    opens the rating of THIS ticket. Gated on comms like every emitter: a
    box without comms ships no row."""
    from app.core.events.service import EVENT_NOTIFICATION_REQUEST, emit_event

    if not comms_configured():
        return
    person = await session.get(User, pointer.user_id)
    reads_ru = (
        person is not None and translation.normalize_language(person.language) == "ru"
    )
    language = "ru" if reads_ru else "en"
    title, body = _RATING_REQUEST_TEXT[language]
    await emit_event(
        session,
        EVENT_NOTIFICATION_REQUEST,
        {
            "idempotency_key": (
                f"aivis:support-rating:{pointer.comms_thread_id}:{version}"
            ),
            "type": RATING_REQUEST_TYPE,
            "target_type": "user",
            "target_value": str(pointer.user_id),
            "title": title,
            "body": body,
            "action_data": {
                "action": OPEN_RATING_ACTION,
                "params": {"id": str(pointer.comms_thread_id)},
            },
        },
    )


async def rate_ticket(
    session: AsyncSession,
    *,
    user: User,
    thread_id: UUID,
    stars: int,
    comment: str | None,
) -> dict[str, Any]:
    """The person rates their own RESOLVED ticket, once.

    404 unless the ticket is the caller's: another person's ticket, a
    history thread, an id nobody has -- one answer, existence does not
    leak. 409 when the ticket is not RESOLVED (back at work, or closed
    another way) or is rated already -- a retry after a lost answer is
    that 409 too, and the screen reads the ratings again.

    ONE WRITE DECIDES, under the row's lock: RESOLVED and still unrated. A
    message of the person reopening the ticket, or a second rating, in the
    same instant comes first or second -- never both through. The rating
    keeps the operator who resolved the ticket at this moment.
    """
    pointer, ticket = await _ticket_by_thread(session, thread_id)
    if pointer is None or ticket is None or pointer.user_id != user.id:
        raise NotFoundError("Ticket not found", code="support_ticket_not_found")
    text = (comment or "").strip() or None
    rated = (
        await session.execute(
            update(SupportTicket)
            .where(
                SupportTicket.support_thread_id == ticket.support_thread_id,
                SupportTicket.status == STATUS_RESOLVED,
                SupportTicket.rating.is_(None),
            )
            .values(
                rating=stars,
                rating_comment=text,
                rating_locale=translation.normalize_language(user.language),
                rated_at=func.now(),
                rated_resolver_user_id=SupportTicket.resolved_by_user_id,
            )
            .returning(SupportTicket.rated_at)
        )
    ).first()
    if rated is None:
        raise ConflictError(
            "Only a resolved ticket not rated yet is rated",
            code="support_ticket_not_ratable",
        )
    logger.info("support_ticket_rated", thread_id=str(thread_id), stars=stars)
    return {
        "id": str(thread_id),
        "stars": stars,
        "comment": text,
        "rated_at": rated[0].isoformat(),
    }


async def my_ratings(session: AsyncSession, *, user: User) -> dict[str, Any]:
    """The caller's ratings: `pending` -- tickets RESOLVED and not rated,
    the ones the conversation asks about, most recently resolved first;
    `rated` -- every ticket they rated, whatever its status now, so a
    rating shows as given after a reload too (owner ruling)."""
    rows = (
        await session.execute(
            select(SupportTicket, SupportThread)
            .join(SupportThread, SupportThread.id == SupportTicket.support_thread_id)
            .where(
                SupportThread.user_id == user.id,
                (
                    (SupportTicket.status == STATUS_RESOLVED)
                    & SupportTicket.rating.is_(None)
                )
                | SupportTicket.rating.is_not(None),
            )
            .order_by(
                SupportTicket.status_changed_at.desc(),
                SupportTicket.support_thread_id.desc(),
            )
        )
    ).all()
    pending = []
    rated = []
    for ticket, pointer in rows:
        if ticket.rating is None:
            pending.append(
                {
                    "id": str(pointer.comms_thread_id),
                    "topic": ticket.topic,
                    "category": ticket.category,
                    "resolved_at": ticket.status_changed_at.isoformat(),
                }
            )
        else:
            rated.append(
                {
                    "id": str(pointer.comms_thread_id),
                    "topic": ticket.topic,
                    "stars": ticket.rating,
                    "comment": ticket.rating_comment,
                    "rated_at": (
                        ticket.rated_at.isoformat() if ticket.rated_at else None
                    ),
                }
            )
    return {"pending": pending, "rated": rated}


def _rating_figures(count: int, total: int | None, top: int | None) -> dict:
    """The rating columns of a statistics row: how many rated, the average
    (two decimals) and the share of 4-5 (0..1, three decimals); null when
    nothing was rated -- no rating is not a zero."""
    if not count:
        return {"rated": 0, "average": None, "share_4_5": None}
    return {
        "rated": count,
        "average": round((total or 0) / count, 2),
        "share_4_5": round((top or 0) / count, 3),
    }


async def support_stats(
    session: AsyncSession, *, created_from: datetime, created_to: datetime
) -> dict[str, Any]:
    """Support over a period of APPEALS -- tickets created in
    [created_from, created_to), the list's own date filter, so the
    categories add up to the list without spam for the same period.

      categories -- all six, zeros included: tickets, and their ratings
                    (rated, average, share of 4-5); spam left out, its
                    rating too.
      total      -- the sum of the categories, the same figures.
      spam       -- the period's spam: the spam tickets that still exist
                    plus the tombstones of those the bin took (by the date
                    of the appeal).
      resolvers  -- per operator a rating is about (rated_resolver), the
                    same rating figures, spam left out; a rating whose
                    operator is gone is in its category, not here.

    History threads have no ticket and are not here: statistics start with
    tickets.
    """
    in_period = (
        SupportTicket.created_at >= created_from,
        SupportTicket.created_at < created_to,
    )
    not_spam = SupportTicket.status != STATUS_SPAM
    top = case((SupportTicket.rating >= 4, 1), else_=0)
    per_category = {
        category: (tickets, rated, total, best)
        for category, tickets, rated, total, best in (
            await session.execute(
                select(
                    SupportTicket.category,
                    func.count(),
                    func.count(SupportTicket.rating),
                    func.sum(SupportTicket.rating),
                    func.sum(top),
                )
                .where(*in_period, not_spam)
                .group_by(SupportTicket.category)
            )
        ).all()
    }
    categories = []
    for category in CATEGORIES:
        tickets, rated, total, best = per_category.get(category, (0, 0, None, None))
        categories.append(
            {
                "category": category,
                "tickets": tickets,
                **_rating_figures(rated, total, best),
            }
        )
    all_rated = sum(per_category.get(c, (0, 0, None, None))[1] for c in CATEGORIES)
    all_total = sum(per_category.get(c, (0, 0, 0, 0))[2] or 0 for c in CATEGORIES)
    all_best = sum(per_category.get(c, (0, 0, 0, 0))[3] or 0 for c in CATEGORIES)
    live_spam = (
        await session.execute(
            select(func.count())
            .select_from(SupportTicket)
            .where(*in_period, SupportTicket.status == STATUS_SPAM)
        )
    ).scalar_one()
    buried_spam = (
        await session.execute(
            select(func.count())
            .select_from(SupportSpamTombstone)
            .where(
                SupportSpamTombstone.appealed_at >= created_from,
                SupportSpamTombstone.appealed_at < created_to,
            )
        )
    ).scalar_one()
    by_resolver = (
        await session.execute(
            select(
                SupportTicket.rated_resolver_user_id,
                func.count(SupportTicket.rating),
                func.sum(SupportTicket.rating),
                func.sum(top),
            )
            .where(
                *in_period,
                not_spam,
                SupportTicket.rating.is_not(None),
                SupportTicket.rated_resolver_user_id.is_not(None),
            )
            .group_by(SupportTicket.rated_resolver_user_id)
        )
    ).all()
    operators: dict[UUID, User] = {}
    if by_resolver:
        operators = {
            u.id: u
            for u in (
                await session.execute(
                    select(User).where(User.id.in_([r[0] for r in by_resolver]))
                )
            ).scalars()
        }
    resolvers = sorted(
        (
            {
                "operator": _person_or_none(operators, operator_id),
                **_rating_figures(count, total, best),
            }
            for operator_id, count, total, best in by_resolver
        ),
        key=lambda r: (-r["rated"], str((r["operator"] or {}).get("user_id"))),
    )
    return {
        "period": {
            "created_from": created_from.isoformat(),
            "created_to": created_to.isoformat(),
        },
        "categories": categories,
        "total": {
            "tickets": sum(c["tickets"] for c in categories),
            **_rating_figures(all_rated, all_total, all_best),
        },
        "spam": {
            "tickets": live_spam + buried_spam,
            "live": live_spam,
            "deleted": buried_spam,
        },
        "resolvers": resolvers,
    }


# ---------------------------------------------------------------------------
# The operator signals (H40 item 8; comms-profile/types.yaml)
# ---------------------------------------------------------------------------

MESSAGE_RECEIVED_TYPE = "support.message_received"
ASSIGNED_TYPE = "support.ticket_assigned"
RELEASED_TYPE = "support.ticket_released"

# What the cabinet shows: the stored title and body, in the support
# language -- the one language support staff read (H39). Telegram renders
# its own sheets (templates/{en,ru}.yaml) in the recipient's language,
# from the variables in action_data.
_SIGNAL_TITLES = {
    MESSAGE_RECEIVED_TYPE: {
        "ru": "Новое сообщение в поддержку",
        "en": "New message to support",
    },
    ASSIGNED_TYPE: {
        "ru": "Вам передали обращение",
        "en": "A support request was handed to you",
    },
    RELEASED_TYPE: {
        "ru": "Обращение вернулось в общий список",
        "en": "A support request is back in the pool",
    },
}

# The one action of every operator signal: the ticket's card. One
# parameter, the comms thread id -- comms' deep-link encoding takes at
# most one, and "open_support_ticket__<uuid>" (57) is within its 64.
OPEN_TICKET_ACTION = "open_support_ticket"


def _display_name(user: User | None) -> str:
    """Who, for a signal: the name, else the e-mail, else the start of the
    id. Never empty -- comms refuses an empty body -- and language-neutral
    on every rung: one signal goes to operators of both languages."""
    if user is None:
        return "?"
    profile = user.profile or {}
    name = " ".join(
        part.strip()
        for part in (profile.get("first_name"), profile.get("last_name"))
        if isinstance(part, str) and part.strip()
    )
    if name:
        return name
    if user.email:
        return user.email
    return str(user.id)[:8]


async def _emit_signal(
    session: AsyncSession,
    *,
    idempotency_key: str,
    type: str,
    target: tuple[str, str],
    thread_id: UUID,
    topic: str,
    sender_name: str,
    actor_name: str | None,
) -> None:
    """One operator signal through the outbox. Gated on comms like every
    emitter (emit_support_membership says why): a box without comms ships
    no row, and a row nobody ships is table growth."""
    from app.core.events.service import EVENT_NOTIFICATION_REQUEST, emit_event

    if not comms_configured():
        return
    language = "ru" if settings.support_language == "ru" else "en"
    label = TOPICS[topic]
    topic_line = label.ru if language == "ru" else label.en
    who = f"{actor_name}: {sender_name}" if actor_name else sender_name
    await emit_event(
        session,
        EVENT_NOTIFICATION_REQUEST,
        {
            "idempotency_key": idempotency_key,
            "type": type,
            "target_type": target[0],
            "target_value": target[1],
            "title": _SIGNAL_TITLES[type][language],
            "body": f"{who} · {topic_line}",
            "action_data": {
                "action": OPEN_TICKET_ACTION,
                "params": {"id": str(thread_id)},
                "sender_name": sender_name,
                "actor_name": actor_name or "",
                "topic_ru": label.ru,
                "topic_en": label.en,
            },
        },
    )


async def _emit_message_received(
    session: AsyncSession,
    user: User,
    *,
    thread_id: UUID,
    message_id: UUID,
    topic: str,
    claimed_by: UUID | None,
) -> None:
    """support.message_received -- one per message of a person, keyed by
    the comms MESSAGE: one message, one signal. Routed by who took the
    ticket: the taker alone, else every operator (the group). No category
    in the profile: no operator can mute it."""
    target = (
        ("user", str(claimed_by))
        if claimed_by is not None
        else ("group", SUPPORT_OPERATORS_GROUP)
    )
    await _emit_signal(
        session,
        idempotency_key=f"aivis:support-message:{message_id}",
        type=MESSAGE_RECEIVED_TYPE,
        target=target,
        thread_id=thread_id,
        topic=topic,
        sender_name=_display_name(user),
        actor_name=None,
    )


async def _emit_handover(
    session: AsyncSession,
    *,
    type: str,
    pointer: SupportThread,
    ticket: SupportTicket,
    actor: User,
    version: int,
    target: tuple[str, str],
) -> None:
    """Tell operators what comms does not: a ticket was handed to one of
    them, or returned to the pool. Keyed by the ticket's version after the
    handover -- one signal per handover, the same document on a repeat."""
    opener = await session.get(User, pointer.user_id)
    await _emit_signal(
        session,
        idempotency_key=f"aivis:{type}:{pointer.comms_thread_id}:{version}",
        type=type,
        target=target,
        thread_id=pointer.comms_thread_id,
        topic=ticket.topic,
        sender_name=_display_name(opener),
        actor_name=_display_name(actor),
    )


# ---------------------------------------------------------------------------
# Section membership (T-67) and the operators group (H40)
# ---------------------------------------------------------------------------


async def emit_support_membership(
    session: AsyncSession, *, user_id: UUID, member: bool = True
) -> None:
    """Tell comms that this person does (or no longer does) support work:
    the section roster AND the operators group, with the same `member`.

    Sent through the OUTBOX, in the caller's transaction, so the fact and
    its announcement commit together: a staff member who exists without a
    membership event would be invisible to the queue until somebody
    noticed.

    TWO DECLARATIONS, ONE PLACE (H40). The roster is who may claim, hand
    over and change the status of a support thread in comms; the group is
    who a signal "to every operator" reaches. They are the same people by
    definition, so they are written together here and nowhere else -- a
    second writer would be a second set that drifts. The pre-H40 staff
    joined the group by migration 0061, as they joined the roster by 0042.

    THE SECTION TRAVELS AS A KEY, never as an id -- the same rule that made
    get_support_section_id an in-process cache. The label rides along
    because this event can be the FIRST mention of the section.

    A section with NO declared members is served by every operator; the
    moment ONE member is declared, everybody else stops serving it. So
    partial declaration is worse than none, which is why the backfills
    emit for every active staff profile in one transaction.

    BOTH DIRECTIONS HAVE A CALLER: `member=True` when a staff member is
    promoted (staff/service.create_staff), `member=False` when one is
    deactivated (staff/service.deactivate_staff).
    """
    from app.core.events.service import (
        EVENT_GROUP_CHANGED,
        EVENT_SECTION_MEMBERSHIP_CHANGED,
        emit_event,
    )

    if not comms_configured():
        # NOTHING IS WRITTEN when this box has no comms address: the relay
        # is disabled by the same empty address, so a row emitted here
        # would sit in the table forever with nobody to ship it. Neither
        # caller breaks: create_staff and deactivate_staff await this for
        # its effect and read nothing back.
        logger.info(
            "support_membership_skipped_no_comms",
            user_id=str(user_id),
            member=member,
        )
        return

    await emit_event(
        session,
        EVENT_SECTION_MEMBERSHIP_CHANGED,
        {
            "section_key": _SUPPORT_SECTION_KEY,
            "section_label": _SUPPORT_SECTION_LABEL,
            "operator_id": str(user_id),
            "member": member,
        },
    )
    await emit_event(
        session,
        EVENT_GROUP_CHANGED,
        {
            "group_key": SUPPORT_OPERATORS_GROUP,
            "recipient_id": str(user_id),
            "member": member,
        },
    )
    if member:
        # A NEW OPERATOR IS NOT SENT comms' OWN SUPPORT PING (owner ruling,
        # H40). comms pings a thread's assignee or the section roster with
        # msg.support_message (category staff_messages) on every message of
        # a client -- and the H40 signals (support.message_received and the
        # two handover signals, below) say all of that and more: to the
        # taker or to every operator, with the person's name and the topic,
        # and opening the ticket's card. Left alone, every person's message
        # would ring an operator twice. Hiding comms' rows in the staff
        # bell instead would leave the bell's count (comms' unread count,
        # which no filter of ours reaches) counting rows nobody sees. So
        # the product mutes the category for the operator: comms then
        # creates no delivery of that ping at all. The profile is not
        # touched -- the mute is the recipient's setting (INTEGRATION.md
        # section 6), and an operator who turns the category back on in
        # their settings gets both pings, by their own choice.
        #
        # Queued here, in the membership's transaction, and carried out by
        # mute.apply_operator_mutes: comms takes preferences only over
        # HTTP, and a brand-new staff member is not a comms recipient until
        # their user_upserted ships -- a PATCH from here would be refused
        # (404) or outlive a rolled-back transaction. Leaving the operators
        # touches nothing: the category concerns operators only.
        await session.execute(
            pg_insert(SupportOperatorMute)
            .values(user_id=user_id, queued_at=func.now(), attempts=0)
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
    logger.info(
        "support_membership_emitted",
        user_id=str(user_id),
        member=member,
    )
