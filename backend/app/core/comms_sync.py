# =============================================================================
# AIVIS.ONE Backend -- "the recipient exists before the first message" (T-64)
# =============================================================================
#
# One function, called from every place a user is created. It lives
# here rather than in each creation site for a reason worth stating: a
# second creation path that forgets the call does not fail anywhere --
# it produces a user whose first notification is dropped by comms
# weeks later, with nothing in this product's logs to connect the two.
#
# THE TWO PATHS, in order of preference:
#   1. SYNCHRONOUS -- call comms and wait. On success the recipient
#      exists now, which is the whole point: the next thing this
#      product does may be to send that user a message.
#   2. OUTBOX -- if the call did not succeed, emit user_upserted into
#      the transactional outbox instead. The relay ships it when comms
#      comes back, so a failed fast path degrades to the slow path
#      rather than to nothing. Both write the same snapshot, and the
#      comms-side upsert is idempotent, so the two can never disagree.
#
# WHY THE CALL SITS INSIDE THE CALLER'S TRANSACTION. The fallback must
# be transactional: an outbox row about a user whose creation later
# rolled back would be a lie this product tells comms about itself.
# Keeping both in one transaction makes that impossible. The cost,
# accepted deliberately: the HTTP call holds the transaction open for
# up to comms_http_timeout_seconds, and a synchronous success followed
# by a failed commit leaves comms holding a recipient for a user that
# never came to exist. That row is inert -- no message will ever be
# addressed to an id no user has -- and the opposite inconsistency
# would not be.
#
# This function never raises. Creating a user must not depend on
# another service being up.
# =============================================================================

from typing import TYPE_CHECKING

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.comms import comms_configured, upsert_recipient, user_snapshot
from app.core.events.service import EVENT_USER_UPSERTED, emit_event

if TYPE_CHECKING:  # pragma: no cover -- annotation only
    from app.modules.users.models import User

logger = structlog.get_logger()


async def ensure_recipient(session: AsyncSession, user: "User") -> bool:
    """Make sure comms knows this user. Returns True if it knows now.

    Call it right after the user row has been flushed (the id must
    exist) and inside that same transaction.

    False is not an error to handle at the call site -- it means the
    recipient is on its way through the outbox instead. The caller
    carries on either way.
    """
    snapshot = user_snapshot(user)

    if not comms_configured():
        # No comms on this box: no call, and NO outbox row either. The
        # relay is disabled in exactly the same situation (its own
        # address is empty too), so a row emitted here would sit in the
        # table forever with nobody to ship it -- growth, not delivery.
        return False

    if await upsert_recipient(user.id, snapshot):
        return True

    # ┌─ KNOWN CEILING ──────────────────────────────────────────────────
    # │ (1) MECHANICS: when comms is unreachable the recipient arrives
    # │     asynchronously, so the guarantee this module exists to give
    # │     -- "the recipient exists before the first message" --
    # │     degrades to best-effort for exactly as long as the outage
    # │     lasts. A notification emitted inside that window can still
    # │     overtake the sync and be dropped by comms (SKIPPED, no
    # │     delivery row, no retry).
    # │ (2) STATUS: acknowledged by design.
    # │ (3) REFERENCE: none, and this is not a deferred task. The
    # │     alternative is failing user creation when comms is down,
    # │     which is a worse product on purpose-built terms: a user who
    # │     cannot register is harmed more than a user whose first
    # │     notification is late. The gap is the price of that ruling,
    # │     not an unfinished piece of it.
    # │ (4) UNCONSERVATION TRIGGER: the first product caller of
    # │     emit_event lands in this tree -- from that moment a real
    # │     message can occupy the window, and the exposure stops being
    # │     theoretical.
    # │ (5) SHAPE OF THE FIX: hold the first message rather than widen
    # │     this path -- an emitter that refuses to emit until the
    # │     recipient is confirmed (or that carries the snapshot with
    # │     it), decided together with that emitter.
    # │ (6) REJECTED, AND WHY. (a) Retrying here: it multiplies the
    # │     registration's wait by the retry count for the same answer,
    # │     and the outbox already retries, from disk, across restarts.
    # │     (b) Failing the user creation: forbidden by the ruling above.
    # │     (c) Emitting the outbox event ALWAYS, alongside a successful
    # │     synchronous call: harmless (the upsert is idempotent) but it
    # │     writes a row and spends a relay pass per registration to
    # │     re-tell comms something it already knows.
    # └─────────────────────────────────────────────────────────────────
    # The wire event carries recipient_id INSIDE its data document,
    # while the HTTP call carries it in the path -- same six fields,
    # two transports, and this is the one line where they differ.
    await emit_event(
        session,
        EVENT_USER_UPSERTED,
        {"recipient_id": str(user.id), **snapshot},
    )
    logger.info(
        "comms_recipient_deferred_to_outbox",
        user_id=str(user.id),
    )
    return False
