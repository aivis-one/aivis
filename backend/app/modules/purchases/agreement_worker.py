# =============================================================================
# AIVIS.ONE Backend -- Agreement Snapshot Worker (H18 P-74)
# =============================================================================
#
# RESPONSIBILITY:
#   Background sweep that fills Purchase.agreement_html for purchases
#   that have a resolved template but no snapshot yet. Called on
#   settings.agreement_snapshot_worker_interval_minutes by the
#   asyncio.Task in main.py lifespan.
#
# WHY THIS FILE EXISTS AT ALL, RATHER THAN A LINE INSIDE
# engine.write_transactions (H18 report, the design that was rejected):
#   Rendering touches MinIO (template.html + assets) and runs a Jinja2
#   template. write_transactions runs under the same per-user
#   pg_advisory_xact_lock submit_kyc takes (purchases/engine.py, step
#   1) -- rendering there would hold that lock for as long as a MinIO
#   round-trip took, blocking the same person's own KYC submission and
#   their own other purchases. That is the exact shape of defect H17
#   P-58 removed from KYC document uploads, on a different lock key.
#   This worker holds no lock at all and runs strictly after the
#   purchase's own transaction has long since committed -- see
#   purchases/models.py's module docstring for the fuller account.
#
# SESSION / LOCKING SHAPE: mirrors core/events/relay.py's
# _publish_batch, not installments/worker.py's per-row reload. One
# session, one transaction: SELECT ... FOR UPDATE SKIP LOCKED claims a
# batch, and every row in it is processed inside that SAME transaction
# before one commit at the end. A second app replica running its own
# sweep claims disjoint rows instead of double-rendering the same one.
# (installments/worker.py splits SELECT and per-row FOR UPDATE across
# two separate sessions because its batch spans a whole day of
# wall-clock time; this sweep's whole pass is seconds, so there is no
# gap for the claim to go stale in.)
#
# POISON ROWS (P-27 class, named in the payments sweeper): a Purchase
# whose template can never render -- a missing declared asset, a body
# that no longer matches its own placeholders -- would otherwise
# occupy a batch slot on every single pass forever.
# agreement_snapshot_attempts is the guard: the SELECT's own WHERE
# excludes a row once attempts reaches
# settings.agreement_snapshot_max_attempts. No exponential backoff
# timer the way the comms outbox has one: that machinery earns its
# cost against an external, at-least-once delivery guarantee; this is
# a purely best-effort cache with a zero-cost, always-correct fallback
# (render_agreement_html renders live on a NULL snapshot, exactly as
# it did before this pass), so the worker's own multi-minute interval
# already throttles retries enough. Giving up on a row costs nothing
# but the caching benefit for that one purchase -- not a KNOWN CEILING
# in the sense of an unresolved gap, since nothing downstream ever
# needs that row's snapshot to exist.
# =============================================================================

import structlog
from jinja2 import UndefinedError
from sqlalchemy import select

from app.core.audit import record_audit
from app.core.config import settings
from app.core.database import get_session_factory
from app.core.exceptions import BadRequestError
from app.core.storage import StorageError
from app.modules.purchases.agreement_service import (
    build_agreement_data_for_snapshot,
    render_agreement_html,
)
from app.modules.purchases.models import Purchase

logger = structlog.get_logger()

# Exceptions render_agreement_html's own docstring documents as
# raiseable from the live-render path it takes on a NULL snapshot.
# These charge an attempt and move to the next row -- a poison row,
# not an infrastructure failure.
_POISON_EXCEPTIONS: tuple[type[Exception], ...] = (
    StorageError,
    BadRequestError,
    UndefinedError,
)


async def run_agreement_snapshot_batch() -> None:
    """One sweep pass: snapshot agreement_html for purchases missing one.

    Owns its own session and commits once at the end of the pass --
    unlike agreement_service.py (read-only, P-01), this file's whole
    reason to exist is to perform the write that module deliberately
    does not.
    """
    factory = get_session_factory()

    async with factory() as session:
        stmt = (
            select(Purchase)
            .where(
                Purchase.agreement_html.is_(None),
                Purchase.purchase_agreement_template_id.is_not(None),
                Purchase.agreement_snapshot_attempts
                < settings.agreement_snapshot_max_attempts,
            )
            .order_by(Purchase.created_at.asc())
            .limit(settings.agreement_snapshot_worker_batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        purchases = result.scalars().all()

        if not purchases:
            return

        snapshotted = 0
        failed = 0

        for purchase in purchases:
            data = await build_agreement_data_for_snapshot(purchase, session)
            if data is None:
                # The template row is gone (ondelete=SET NULL fired
                # between this SELECT and now) or was never valid --
                # not this row's fault, no attempt charged. The
                # read-time fallback in render_agreement_html already
                # handles a NULL template_id on its own; there is
                # nothing more for this worker to try this pass.
                continue

            try:
                html = await render_agreement_html(data, session)
            except _POISON_EXCEPTIONS as exc:
                purchase.agreement_snapshot_attempts += 1
                gave_up = (
                    purchase.agreement_snapshot_attempts
                    >= settings.agreement_snapshot_max_attempts
                )
                logger.error(
                    "agreement_snapshot_failed",
                    purchase_id=str(purchase.id),
                    attempts=purchase.agreement_snapshot_attempts,
                    gave_up=gave_up,
                    error=str(exc),
                )
                await record_audit(
                    session=session,
                    event="purchase.agreement_snapshot_failed",
                    actor_id=purchase.investor_id,
                    actor_type="system",
                    target_type="purchase",
                    target_id=purchase.id,
                    data={
                        "attempts": purchase.agreement_snapshot_attempts,
                        "gave_up": gave_up,
                        "template_id": str(
                            purchase.purchase_agreement_template_id
                        ),
                    },
                )
                failed += 1
                continue

            purchase.agreement_html = html
            snapshotted += 1

        await session.commit()

        if snapshotted or failed:
            logger.info(
                "agreement_snapshot_batch_completed",
                snapshotted=snapshotted,
                failed=failed,
            )
