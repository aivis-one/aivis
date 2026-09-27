# =============================================================================
# AIVIS.ONE Backend -- "comms knows the person as this product does"
#                       (T-64, extended H23 P-113)
# =============================================================================
#
# One function, sync_recipient, called from every place a user is
# created AND from every place a field of the snapshot changes: the
# language, active (self-deactivation, a staff block, an unblock). It
# lives here rather than in each site for a reason worth stating: a site
# that forgets the call does not fail anywhere -- it leaves comms with a
# person who is gone, blocked or speaking another language, and comms
# rechecks `active` against that stale copy before every send.
#
# WHERE THE CALLS ARE, and how that list was established (H23): the
# snapshot reads four facts -- credentials.telegram.id, credentials.
# email.email (the User.email property), language, is_active. Every
# write to them was searched for in every form: attribute assignment,
# set_jsonb("credentials", ...), User(...) constructors, update(User)
# and raw UPDATE users. The creation sites are auth/service.py (email
# and telegram registration) and companies/service.py (two); the change
# sites are users/service.py (language, self-deactivation) and
# staff/admin_service.py (block, unblock). Nothing else writes those
# fields: TOTP, onboarding and password reset write credentials keys the
# snapshot does not read, and the product has no email change and no
# telegram link for an existing account.
#
# THE VERSION. comms 3.0.0 applies a snapshot only when its version is
# higher than the stored one, and treats the same version with other
# content as a conflict. The version is users.comms_snapshot_version,
# raised HERE and nowhere else, by an UPDATE ... RETURNING inside the
# caller's transaction: two concurrent changes of one person serialise
# on the row lock, so each gets its own number in commit order.
#
# THE TWO PATHS, in order of preference:
#   1. SYNCHRONOUS -- call comms and wait. On success the recipient
#      exists now, which is the whole point: the next thing this
#      product does may be to send that user a message.
#   2. OUTBOX -- if the call did not succeed, emit user_upserted into
#      the transactional outbox instead. The relay ships it when comms
#      comes back, so a failed fast path degrades to the slow path
#      rather than to nothing. Both write the same snapshot -- one dict,
#      one version -- so the two can never disagree, and a late event is
#      refused by comms as older than what it holds.
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
# The same order has a second price since the snapshot is versioned, and
# it is accepted with the first: a synchronous success followed by a
# rollback leaves comms holding version N with content the database
# never committed, while the counter rolls back to N-1. The next change
# of that person is sent as N again with other content -- a `conflict`,
# logged as comms_upsert_version_conflict and not retried -- and the
# change after it, N+1, is applied. One change is lost until the next.
#
# This function never raises. Creating a user must not depend on
# another service being up.
# =============================================================================

from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core.comms import (
    UpsertOutcome,
    comms_configured,
    upsert_recipient,
    user_snapshot,
)
from app.core.events.service import EVENT_USER_UPSERTED, emit_event

if TYPE_CHECKING:  # pragma: no cover -- annotation only
    from app.modules.users.models import User

logger = structlog.get_logger()


async def sync_recipient(session: AsyncSession, user: "User") -> bool:
    """Tell comms who this person is now. Returns True if comms knows now.

    Call it right after the user row has been flushed (the id must
    exist) and inside the transaction that created or changed the
    person -- see the module header for where, and why there.

    False is not an error to handle at the call site -- it means the
    snapshot is on its way through the outbox instead, or that comms
    already holds something newer or refused this version as a defect
    of ours (logged). The caller carries on either way.
    """
    if not comms_configured():
        # No comms on this box: no call, and NO outbox row either. The
        # relay is disabled in exactly the same situation (its own
        # address is empty too), so a row emitted here would sit in the
        # table forever with nobody to ship it -- growth, not delivery.
        # No version is spent either: nothing is sent under it.
        return False

    # Raw SQL because core must not import a product model at runtime
    # (core/comms.py says the same about User). RETURNING under the row
    # lock the UPDATE takes: a concurrent change of the same person
    # waits for this transaction and then gets the next number.
    version = (
        await session.execute(
            text(
                "UPDATE users "
                "SET comms_snapshot_version = comms_snapshot_version + 1 "
                "WHERE id = :id "
                "RETURNING comms_snapshot_version"
            ),
            {"id": user.id},
        )
    ).scalar_one()
    # Keep the loaded object truthful without making it dirty: the row
    # already holds this value, and a flush must not write it again.
    set_committed_value(user, "comms_snapshot_version", version)

    snapshot = user_snapshot(user, version)

    outcome = await upsert_recipient(user.id, snapshot)
    if outcome is UpsertOutcome.STORED:
        return True
    if outcome is not UpsertOutcome.UNDELIVERED:
        # SUPERSEDED or CONFLICT: the outbox would meet the same answer.
        return False

    # ┌─ KNOWN CEILING ──────────────────────────────────────────────────
    # │ (1) MECHANICS: when comms is unreachable the recipient arrives
    # │     asynchronously, so the guarantee this module exists to give
    # │     -- "the recipient exists before the first message" --
    # │     degrades to best-effort for exactly as long as the outage
    # │     lasts. A notification that overtakes the sync is dropped by
    # │     comms (SKIPPED, no delivery row, no retry).
    # │
    # │     NARROWED, 2026-09-19, BY THE EMITTER THIS MARKER WAS
    # │     WAITING FOR (auth/service.py's registration email). An
    # │     emitter that writes its own outbox row in the SAME
    # │     transaction, AFTER this function, cannot overtake the sync
    # │     in the ordinary case: this row is inserted first and takes
    # │     the lower BIGSERIAL id, and the relay publishes in id order
    # │     (core/events/relay.py). So for those emitters the window is
    # │     closed by construction, not by luck.
    # │
    # │     WHAT REMAINS OPEN, AND IT IS THE WHOLE OF THIS MARKER'S
    # │     SUBJECT NOW: the relay's SELECT excludes a row whose
    # │     next_attempt_at is in the future, and keeps shipping the
    # │     rows behind it -- its own header calls that inversion
    # │     accepted. So if THIS row is charged an attempt and put into
    # │     backoff, a notification emitted after it publishes first
    # │     and lands on a recipient comms has not been told about. The
    # │     exposure is no longer "any notification during an outage";
    # │     it is "any notification behind a poisoned user_upserted".
    # │ (2) STATUS: acknowledged by design.
    # │ (3) REFERENCE: none, and this is not a deferred task. The
    # │     alternative is failing user creation when comms is down,
    # │     which is a worse product on purpose-built terms: a user who
    # │     cannot register is harmed more than a user whose first
    # │     notification is late. The gap is the price of that ruling,
    # │     not an unfinished piece of it.
    # │ (4) UNCONSERVATION TRIGGER: this row is seen in backoff --
    # │     a `user_upserted` outbox row with next_attempt_at set and
    # │     attempts > 0, or the relay logging a poison charge against
    # │     one. The old trigger ("the first product caller of
    # │     emit_event lands in this tree") has FIRED and is spent: the
    # │     caller arrived and closed the ordinary case, so what is
    # │     left to watch for is the one path it did not close.
    # │ (5) SHAPE OF THE FIX: do not let a poisoned recipient row be
    # │     overtaken -- either the relay stops the pass on a
    # │     user_upserted in backoff instead of shipping past it, or a
    # │     notification for a recipient whose sync row is still
    # │     pending is held behind it. Either is a change in the relay,
    # │     not in this module: the ordering that closed the ordinary
    # │     case is the relay's, and so is the exception to it.
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
    # while the HTTP call carries it in the path -- same six snapshot
    # fields, version included, two transports, and this is the one line
    # where they differ.
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
