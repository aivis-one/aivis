# =============================================================================
# AIVIS.ONE Backend -- Support: muting comms' own ping for operators (H40)
# =============================================================================
#
# WHY (owner ruling, H40): comms pings a thread's assignee, or the section
# roster, with msg.support_message (category `staff_messages`) on every
# message of a client. The H40 operator signals -- support.message_received,
# support.ticket_assigned, support.ticket_released (service.py) -- cover
# that ping entirely and say more. So an operator is not sent comms' ping
# at all: the product turns the category off in the operator's comms
# preferences (comms deploy/INTEGRATION.md section 6), and comms creates
# no delivery of it. Hiding the rows in the staff bell instead would have
# left the bell's count -- comms' unread count -- counting rows nobody
# sees. The profile is not touched: a mute is the recipient's own setting,
# and an operator who turns the category back on gets both pings.
#
# HOW: a row in support_operator_mutes is written with the membership, in
# its transaction (service.emit_support_membership, member=True; for the
# staff who existed before, migration 0062). This step carries the rows
# out: PATCH /api/v1/recipients/{id}/preferences with the one category
# off. comms' 200 deletes the row. Anything else leaves it, attempts + 1,
# for the next step:
#
#   not_found -- the recipient is not in comms yet (a new staff member's
#     user_upserted still in the outbox): it will be;
#   comms down or slow (CommsUnavailableError, 502/504): it will be up;
#   any other refusal (a 422 -- a category comms does not know) is a
#     defect, logged as an ERROR at once -- and kept, so the fix of the
#     defect is what carries it out.
#
# Retries have no limit -- a PATCH is cheap and the rows are a handful --
# but are not silent: from STUCK_AFTER_ATTEMPTS on, every further failure
# is one warning with the person and the class of the refusal, so a mute
# that does not take is visible in the log.
#
# ONE ROW, ONE TRANSACTION, the row locked FOR UPDATE SKIP LOCKED across
# its PATCH: workers running the step at once take different rows (and a
# PATCH is idempotent anyway). The lock blocks only a membership of the
# SAME person written in the same moment (its ON CONFLICT DO NOTHING waits
# for this row) -- for as long as one PATCH takes.
# =============================================================================

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import delete, select, update

from app.core.comms import CommsRejectedError, CommsUnavailableError, comms_request
from app.core.config import settings
from app.core.database import get_session_factory
from app.modules.support.models import SupportOperatorMute

logger = structlog.get_logger()

# The comms category of msg.support_message (comms-profile/types.yaml).
STAFF_MESSAGES_CATEGORY = "staff_messages"

# Rows carried out per step at most.
MUTE_BATCH = 50

# From this many failed attempts on, each further failure is a warning.
STUCK_AFTER_ATTEMPTS = 30

# The refusals that are a state of the world, not a defect: the recipient
# comms has not been sent yet.
_TRANSIENT_CLASSES = frozenset({"not_found"})


def _preferences_path(user_id: UUID) -> str:
    return f"/api/v1/recipients/{user_id}/preferences"


async def _apply_one(tried: set[UUID]) -> bool | None:
    """Take one row this step has not tried yet and carry it out; its id
    joins `tried`. None -- no such row was free; True -- the mute was
    taken; False -- it was not, the row stays for the next step."""
    factory = get_session_factory()
    async with factory() as session, session.begin():
        query = select(SupportOperatorMute)
        if tried:
            query = query.where(SupportOperatorMute.user_id.not_in(tried))
        row = (
            await session.execute(
                query.order_by(
                    SupportOperatorMute.queued_at, SupportOperatorMute.user_id
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        user_id, attempts = row.user_id, row.attempts
        tried.add(user_id)
        refusal: str | None = None
        transient = True
        try:
            await comms_request(
                "PATCH",
                _preferences_path(user_id),
                json={"categories": {STAFF_MESSAGES_CATEGORY: False}},
            )
        except CommsUnavailableError as exc:
            refusal = exc.code
        except CommsRejectedError as exc:
            refusal = exc.error_class
            transient = exc.error_class in _TRANSIENT_CLASSES
        if refusal is None:
            await session.execute(
                delete(SupportOperatorMute).where(
                    SupportOperatorMute.user_id == user_id
                )
            )
            logger.info("support_operator_muted", user_id=str(user_id))
            return True
        attempts += 1
        await session.execute(
            update(SupportOperatorMute)
            .where(SupportOperatorMute.user_id == user_id)
            .values(attempts=attempts, last_error_at=datetime.now(UTC))
        )
        if not transient:
            logger.error(
                "support_operator_mute_refused",
                user_id=str(user_id),
                refusal=refusal,
                attempts=attempts,
            )
        elif attempts >= STUCK_AFTER_ATTEMPTS:
            logger.warning(
                "support_operator_mute_stuck",
                user_id=str(user_id),
                refusal=refusal,
                attempts=attempts,
            )
        return False


async def apply_operator_mutes(*, batch: int = MUTE_BATCH) -> int:
    """One step: every queued mute tried once, up to `batch` of them.
    Returns how many comms took. A row that failed stays for the next
    step; this one does not try it again (it would spin while comms is
    down)."""
    tried: set[UUID] = set()
    taken = 0
    while len(tried) < batch:
        outcome = await _apply_one(tried)
        if outcome is None:
            break
        taken += int(outcome)
    return taken


async def run_support_operator_mutes() -> None:
    """The lifespan task (main.py): one step every
    support_operator_mute_interval_seconds, until cancelled. A failed step
    is logged and the next one tries again -- what it did not do is still
    in the table."""
    logger.info(
        "support_operator_mutes_started",
        interval=settings.support_operator_mute_interval_seconds,
    )
    while True:
        try:
            await apply_operator_mutes()
        except asyncio.CancelledError:
            logger.info("support_operator_mutes_stopped")
            raise
        except Exception:
            logger.exception("support_operator_mutes_error")
        try:
            await asyncio.sleep(settings.support_operator_mute_interval_seconds)
        except asyncio.CancelledError:
            logger.info("support_operator_mutes_stopped")
            raise
