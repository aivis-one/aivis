# =============================================================================
# AIVIS.ONE Backend -- Support: the user side of the request channel (T-65)
# =============================================================================
#
# A PROXY, not a store. The conversation lives in comms; this module
# stamps who the caller is, checks that the thread they name is theirs,
# and forwards. The only thing kept locally is the pointer row (models.py).
#
# THE SHAPE OF A SUPPORT CONVERSATION, AND WHY THIS ONE
# -----------------------------------------------------
# A thread is created with operator_kind="section", kind="dm" and NO
# subject_ref. Two independent choices, each with its own reason.
#
#   operator_kind="section" -- the request goes to a POOL, not to a named
#   employee. A user thread in comms is pre-assigned to its operator at
#   creation and can never be claimed by anyone else, which would mean
#   picking the person who answers at the moment the person asks -- before
#   anyone knows what the question is or who is on shift.
#
#   kind="dm" -- ONE eternal conversation per user, not a new thread per
#   request. comms dedups a subjectless dm to a single thread per (client,
#   operator) pair, so opening the channel twice returns the same thread,
#   and the pointer table stays at one row per user. A subjectless
#   "ticket" would do the opposite by construction -- a fresh thread every
#   time, no dedup, a table that grows per button press.
#
#   Beyond the mechanics: this channel is also where selling happens. A
#   sales conversation is a continuing relationship with one history, not
#   a series of closed tickets that lose each other.
#
# WHAT HAPPENS WHEN A THREAD IS CLOSED
# ------------------------------------
# Staff can close a thread (their side is a later delivery; comms already
# has the verb). Two consequences follow, and they are the accepted price
# of the section form:
#
#   1. comms flags EVERY closing section thread as notifiable and its
#      close pass sends msg.thread_closed to the client. The flag keys on
#      the OPERATOR FORM only -- dm-versus-ticket does not affect it -- so
#      choosing the pool means choosing this notice. The user can silence
#      it, but only together with the replies themselves: our profile
#      files both under the support_messages category, because a mute that
#      silenced answers while letting the closing notice through would be
#      a defect rather than a preference.
#
#   2. A CLOSED THREAD IS NOT AN ENDING. comms has no manual reopen at
#      all -- closed has an empty set of allowed manual transitions -- but
#      a message from the CLIENT reopens it automatically and clears any
#      pending close notice. So a user writing into a thread staff closed
#      simply continues the conversation: send_support_message needs no
#      special case, and there is deliberately no "reopen" endpoint here,
#      because writing IS the reopen.
#
# THE SECTION ID IS RESOLVED, NEVER STORED
# ----------------------------------------
# comms' create-or-find section endpoint is called for the key below and
# the answer is cached in process memory only. It must not survive a comms
# teardown in any form -- not in .env, not in a table, not in a migration
# -- because a reinstalled comms hands out a different id and a persisted
# copy would point at nothing. No lock guards the cache: the endpoint is
# create-or-find on comms' side, so two concurrent first callers get the
# same row, and arbitrating that race is comms' job, not ours.
# =============================================================================

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.comms import (
    CommsRejectedError,
    CommsUnavailableError,
    comms_request,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.support.dependencies import SupportOperator
from app.modules.support.models import SupportThread
from app.modules.users.models import User

logger = structlog.get_logger()

_SECTIONS_PATH = "/api/v1/sections"
_THREADS_PATH = "/api/v1/threads"

# The comms section every support request lands in. English on purpose:
# the label is shown to whoever administers comms, never in this product.
_SUPPORT_SECTION_KEY = "support"
_SUPPORT_SECTION_LABEL = "Support"

# In-process cache ONLY (see module header). Reset on every restart; the
# next call re-resolves it.
_support_section_id: UUID | None = None


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
# Pointer
# ---------------------------------------------------------------------------


async def _pointer_for_user(
    session: AsyncSession, user_id: UUID
) -> SupportThread | None:
    """This user's pointer row, or None."""
    result = await session.execute(
        select(SupportThread).where(SupportThread.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _require_own_thread(
    session: AsyncSession, *, user: User, thread_id: UUID
) -> SupportThread:
    """Resolve a thread id from the wire to THIS user's pointer, or 404.

    Both predicates in ONE query on purpose: a thread that does not
    exist and a thread that belongs to somebody else must be
    indistinguishable from the outside. 404 rather than 403 for the same
    reason -- a 403 would confirm that the id names a real conversation.

    This is the check that makes a guessed thread id useless. comms
    trusts whatever actor we send it, so it is the only one there is.
    """
    result = await session.execute(
        select(SupportThread).where(
            SupportThread.comms_thread_id == thread_id,
            SupportThread.user_id == user.id,
        )
    )
    pointer = result.scalar_one_or_none()
    if pointer is None:
        raise NotFoundError("Support thread not found")
    return pointer


async def _remember_thread(
    session: AsyncSession, *, user: User, thread_id: UUID
) -> None:
    """Point this user's row at `thread_id` -- insert, or re-point.

    Three states, all reachable:
      - no row yet -> insert;
      - a row already naming this thread -> nothing to do;
      - a row naming a DIFFERENT thread -> re-point and say so loudly.
        Not a corner case: a comms reinstall empties its database, and
        the next create-or-get returns a brand-new thread id for the
        same user. Keeping the old id would leave the pointer aimed at
        a thread that no longer exists, which reads as "your history
        vanished" and answers no ownership question correctly.

    The insert runs in a SAVEPOINT: two concurrent first opens both see
    no row, and the loser of uq_support_threads_user must not poison the
    caller's transaction.
    """
    pointer = await _pointer_for_user(session, user.id)

    if pointer is None:
        try:
            async with session.begin_nested():
                session.add(
                    SupportThread(
                        user_id=user.id, comms_thread_id=thread_id
                    )
                )
                await session.flush()
        except IntegrityError:
            pointer = await _pointer_for_user(session, user.id)
            if pointer is None:
                raise
            logger.info(
                "support_thread_insert_race_lost",
                user_id=str(user.id),
                thread_id=str(thread_id),
            )
        else:
            return

    if pointer.comms_thread_id != thread_id:
        logger.warning(
            "support_thread_repointed",
            user_id=str(user.id),
            old_thread_id=str(pointer.comms_thread_id),
            new_thread_id=str(thread_id),
        )
        pointer.comms_thread_id = thread_id
        await session.flush()


# ---------------------------------------------------------------------------
# The five verbs
# ---------------------------------------------------------------------------


async def open_support_thread(
    session: AsyncSession, *, user: User
) -> dict[str, Any]:
    """Open the caller's support conversation, or return the existing one.

    Nothing about WHO this is comes from the request: `client` is the
    session's user id and the operator is the support section. There is
    no topic, subject or title on the wire either -- comms stores a
    title only on the insert path, so a topic accepted here would work
    once and silently do nothing on every later call.

    comms is called BEFORE the pointer is written, and that order is the
    point: a pointer to a thread that may not exist is worse than no
    pointer at all.
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
                "kind": "dm",
            },
        )
    except CommsRejectedError as exc:
        if exc.status_code == 404:
            # comms delivers to KNOWN recipients only, and this user is
            # not one yet: the synchronous upsert at registration failed
            # and the outbox has not caught up. Transient, and not the
            # user's doing -- so it is reported as "not ready", never as
            # comms' own wording about a missing recipient row.
            logger.warning(
                "support_recipient_not_synced", user_id=str(user.id)
            )
            raise CommsUnavailableError(
                message="Support is not ready for this account yet",
                code="comms_recipient_pending",
            ) from exc
        raise

    thread_id = _uuid_from_payload(payload, "id", "thread")
    await _remember_thread(session, user=user, thread_id=thread_id)

    logger.info(
        "support_thread_opened",
        user_id=str(user.id),
        thread_id=str(thread_id),
        created=bool(payload.get("created")),
    )

    # `created` is a seam detail for THIS function to act on (today: to
    # log), not the caller's business -- and the next delivery, which
    # notifies staff of a new request, is the one that will need it.
    return {k: v for k, v in payload.items() if k != "created"}


async def list_support_threads(
    session: AsyncSession, *, user: User
) -> dict[str, Any]:
    """The caller's own conversations, from the local pointer.

    comms is not asked WHICH threads are the user's -- it cannot answer
    that (see models.py) -- only how much is unread in the ones we
    already know about.

    IF COMMS IS DOWN THE LIST STILL ANSWERS, without the unread key. The
    rows are ours and remain true; an unread count is an enrichment, and
    the alternative -- failing a read the product can serve, or printing
    a zero we did not measure -- is worse than an absent key. Absence
    also matches comms' own rule for a thread the participant does not
    take part in: no key, never a silent zero.
    """
    result = await session.execute(
        select(SupportThread)
        .where(SupportThread.user_id == user.id)
        .order_by(SupportThread.created_at)
    )
    pointers = list(result.scalars().all())
    rows: list[dict[str, Any]] = [
        {
            "id": str(pointer.comms_thread_id),
            "opened_at": (
                pointer.created_at.isoformat()
                if pointer.created_at is not None
                else None
            ),
        }
        for pointer in pointers
    ]
    if not rows:
        return {"threads": []}

    try:
        payload = await comms_request(
            "POST",
            f"{_THREADS_PATH}/unread-counts",
            json={
                "participant": str(user.id),
                "thread_ids": [row["id"] for row in rows],
            },
        )
    except (CommsUnavailableError, CommsRejectedError):
        logger.warning("support_unread_unavailable", user_id=str(user.id))
        return {"threads": rows}

    counts = payload.get("counts") if isinstance(payload, dict) else None
    if not isinstance(counts, dict):
        return {"threads": rows}

    return {
        "threads": [
            {**row, "unread": counts[row["id"]]}
            if row["id"] in counts
            else row
            for row in rows
        ]
    }


async def get_support_messages(
    session: AsyncSession,
    *,
    user: User,
    thread_id: UUID,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    """One of the caller's own threads, newest messages first."""
    await _require_own_thread(session, user=user, thread_id=thread_id)

    params: dict[str, Any] = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    return await comms_request(
        "GET", f"{_THREADS_PATH}/{thread_id}/messages", params=params
    )


async def send_support_message(
    session: AsyncSession, *, user: User, body: str
) -> dict[str, Any]:
    """Write one message into the caller's own conversation.

    NO THREAD ID ON THE WIRE. There is exactly one conversation per user
    and it is resolved from the pointer, so there is nothing here for a
    caller to point somewhere else.

    404 if the user has never opened the channel: the client opens it
    first (the call is idempotent and cheap). Auto-opening here was
    rejected -- it would make a failed open indistinguishable from a
    failed send, and the person needs to know which one happened.

    A CLOSED THREAD NEEDS NO SPECIAL CASE: comms reopens it on a client
    message and clears any pending close notice.
    """
    pointer = await _pointer_for_user(session, user.id)
    if pointer is None:
        raise NotFoundError("Open a support request before sending a message")

    return await comms_request(
        "POST",
        f"{_THREADS_PATH}/{pointer.comms_thread_id}/messages",
        json={"sender": str(user.id), "body": body},
    )


async def mark_support_thread_read(
    session: AsyncSession, *, user: User, thread_id: UUID
) -> dict[str, Any]:
    """Advance the caller's read pointer; returns the fresh unread count.

    `last_read_at` is NOT accepted from the wire and NOT sent: comms
    stamps now. Accepting one would add a field to argue about (comms
    clamps a future value anyway) in exchange for nothing the product
    needs.
    """
    await _require_own_thread(session, user=user, thread_id=thread_id)

    return await comms_request(
        "POST",
        f"{_THREADS_PATH}/{thread_id}/read",
        json={"participant": str(user.id)},
    )


# ---------------------------------------------------------------------------
# The operator side (T-66)
# ---------------------------------------------------------------------------
#
# WHERE THE TWO SIDES DIFFER, AND WHY.
#
# The user side reads its list from the LOCAL POINTER because comms
# cannot answer "which threads are this client's". The operator side does
# the opposite and reads from comms, because that question -- "what is in
# my queue" -- is exactly what comms' list endpoint answers, and the
# answer depends on live state (who claimed what) that this product does
# not hold.
#
# WHAT EACH OPERATOR SEES is decided by list_visible_threads in comms
# (messaging/operators.py), not here:
#
#   visible(me) = assignee == me OR (section thread AND unassigned)
#
# so a plain operator gets the unclaimed pool plus their own claimed
# threads, and a thread claimed by a colleague disappears from their list
# entirely. is_supervisor=true skips that filter and returns every
# thread there is. Which is why is_supervisor is computed in
# support/dependencies.py from the staff profile and can never arrive
# from a request.
#
# WHAT COMMS DOES NOT ENFORCE, AND WE DO NOT EITHER (recorded because the
# opposite is the natural assumption): can_operate admits ANY operator on
# a SECTION thread -- v1 section membership is trivial, every agent
# serves every section -- so comms will let any operator change the
# status of any support thread, claimed by them or not. Closing is
# therefore open to every active support operator, and this module adds
# no check of its own. Enforcing "only the claimer closes" would need the
# thread's assignee, which comms exposes only through the list or the
# claim response; getting it would mean either mirroring assignee locally
# (a second copy of somebody else's state, stale after a comms rebuild)
# or calling create-or-get on a read path (which silently CREATES a
# thread against a rebuilt comms -- rejected on the user side in T-65 for
# that reason). The exposure is small: a plain operator never sees a
# colleague's claimed thread, so they have no id to aim at. Messages are
# a different matter and ARE gated -- by comms itself, see
# reply_to_support_thread.


async def _require_known_thread(
    session: AsyncSession, thread_id: UUID
) -> SupportThread:
    """Resolve a thread id from the wire to a KNOWN support thread, or 404.

    The operator boundary, and the reason it is not the same function as
    the user side's: an operator serves everybody, so ownership is not
    the question -- existence in OUR pointer table is. Rows land there
    only through open_support_thread, so a row here is proof the id names
    a support conversation this product created, and a guessed or
    foreign id never reaches comms at all.
    """
    result = await session.execute(
        select(SupportThread).where(
            SupportThread.comms_thread_id == thread_id
        )
    )
    pointer = result.scalar_one_or_none()
    if pointer is None:
        raise NotFoundError("Support thread not found")
    return pointer


async def list_operator_threads(
    *, operator: SupportOperator, limit: int, cursor: str | None
) -> dict[str, Any]:
    """The operator's queue, straight from comms.

    Both trusted parameters are stamped here: `operator` is the session's
    id and `is_supervisor` is what the staff profile resolved to. Neither
    is a function argument a router could pass through from a request.

    with_unread is asked for so a rendered list costs one call instead of
    one per row. POOL ROWS WILL NOT CARRY IT, ever: comms attaches the
    count only to threads the operator takes part in, and an unclaimed
    section thread belongs to nobody -- assignee empty, operator_value a
    section id. So "no unread key" on a pool row is the normal state and
    not a gap to fill with a zero.
    """
    params: dict[str, Any] = {
        "operator": str(operator.id),
        "is_supervisor": operator.is_supervisor,
        "with_unread": True,
        "limit": limit,
    }
    if cursor is not None:
        params["cursor"] = cursor
    return await comms_request("GET", _THREADS_PATH, params=params)


async def claim_support_thread(
    session: AsyncSession, *, operator: SupportOperator, thread_id: UUID
) -> dict[str, Any]:
    """Take an unclaimed conversation, or say who already has it.

    comms answers {claimed, thread}: `claimed` is True only for the call
    that won the conditional UPDATE (assignee IS NULL), so a repeat by
    the SAME operator comes back False with themselves as assignee --
    that is idempotence, not failure, and it returns 200. A False with
    somebody else's assignee is a real conflict and returns 409 rather
    than a bare 500 or a misleading success.

    The two cases are told apart by the assignee comms returns, so no
    local copy of who-owns-what is needed. A claimed=False with no
    assignee at all falls into the conflict branch too, on purpose: there
    is no state comms can produce where the thread is unowned AND the
    claim failed, and inventing a branch for it would document a state
    that cannot happen.
    """
    await _require_known_thread(session, thread_id)

    payload = await comms_request(
        "POST",
        f"{_THREADS_PATH}/{thread_id}/claim",
        json={"operator": str(operator.id)},
    )
    thread = payload.get("thread") if isinstance(payload, dict) else None
    if not isinstance(thread, dict):
        logger.error("comms_payload_malformed", what="claim", key="thread")
        raise CommsUnavailableError()

    if bool(payload.get("claimed")):
        logger.info(
            "support_thread_claimed",
            thread_id=str(thread_id),
            operator_id=str(operator.id),
        )
        return thread

    if str(thread.get("assignee")) == str(operator.id):
        return thread

    raise ConflictError(
        "This request has already been taken by another operator",
        code="support_thread_already_claimed",
    )


async def reply_to_support_thread(
    session: AsyncSession,
    *,
    operator: SupportOperator,
    thread_id: UUID,
    body: str,
) -> dict[str, Any]:
    """Answer as this operator.

    WRITE-AUTHZ IS NOT OURS TO GRANT and is not re-implemented here:
    comms' can_post_message admits the thread's client or its ASSIGNEE
    and nobody else -- there is no supervisor bypass -- so an operator
    who has not claimed the conversation is refused by comms with a 403.
    That 403 is forwarded into this module (forward_403) instead of being
    mapped to "service unavailable", and turned into a 409 that says what
    to do about it: claim first.

    409 rather than 403 because the caller's ROLE is fine -- it is the
    state that is wrong, and the same person becomes allowed the moment
    they claim. A 403 would read as "not for people like you".

    A closed thread does NOT reopen on this message: comms revives a
    thread only for a message from the CLIENT.
    """
    await _require_known_thread(session, thread_id)

    try:
        return await comms_request(
            "POST",
            f"{_THREADS_PATH}/{thread_id}/messages",
            json={"sender": str(operator.id), "body": body},
            forward_403=True,
        )
    except CommsRejectedError as exc:
        if exc.status_code == 403:
            raise ConflictError(
                "Claim this request before replying to it",
                code="support_thread_not_claimed",
            ) from exc
        raise


async def set_support_thread_status(
    session: AsyncSession,
    *,
    operator: SupportOperator,
    thread_id: UUID,
    status: str,
) -> dict[str, Any]:
    """Move a conversation along the status matrix.

    THE TRANSITION IS COMMS' TO VALIDATE, and the request is a target
    state rather than a written field: set_status walks the D5 matrix --
    open -> resolved, open -> closed, resolved -> closed, and X -> X as a
    successful no-op. Everything else is refused with a 422, including
    every backward move: a MANUAL reopen does not exist at all. Only a
    message from the client reopens a thread, which is why our schema
    does not offer `open` as a target -- see schemas.SetStatusIn.

    Reaching `closed` on a section thread also arms comms' close notice
    to the client (msg.thread_closed). That is the price of the pooled
    form chosen in T-65, paid here.
    """
    await _require_known_thread(session, thread_id)

    return await comms_request(
        "POST",
        f"{_THREADS_PATH}/{thread_id}/status",
        json={"operator": str(operator.id), "status": status},
    )
