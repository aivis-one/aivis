# =============================================================================
# CBSHOME Backend -- Installment Worker (Sprint 6.2)
# =============================================================================
#
# RESPONSIBILITY:
#   Batch processing for installment daemon. Called daily at
#   INSTALLMENT_WORKER_HOUR by the asyncio.Task in main.py lifespan.
#
# ALGORITHM:
#   1. Find scheduled/overdue tranches with due_date <= today -> try to pay
#   2. Find overdue tranches with due_date + DEFAULT_DAYS <= today -> default
#
# SESSION MANAGEMENT:
#   Each tranche/default is processed in its own session+transaction.
#   Failure on one tranche does not roll back others.
#   Uses get_session_factory() -- same pattern as confirmation worker.
# =============================================================================

from datetime import date, datetime, timedelta, UTC

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_session_factory
from app.modules.installments.constants import (
    InstallmentPlanStatus,
    InstallmentTrancheStatus,
)
from app.modules.installments.models import InstallmentPlan, InstallmentTranche
from app.modules.installments.service import default_plan, pay_tranche

logger = structlog.get_logger()


async def run_installment_batch() -> None:
    """Process due tranches and defaults.

    Called once per day by the installment daemon.
    Each tranche is processed in its own DB transaction.
    """
    today = datetime.now(UTC).date()

    # -- Phase 1: Pay due tranches --
    await _process_due_tranches(today)

    # -- Phase 2: Default overdue plans --
    await _process_defaults(today)


async def _process_due_tranches(today: date) -> None:
    """Find and pay tranches that are due today or earlier."""
    factory = get_session_factory()

    # Find due tranches in a read session.
    async with factory() as session:
        stmt = (
            select(InstallmentTranche.id, InstallmentTranche.plan_id)
            .where(
                InstallmentTranche.status.in_([
                    InstallmentTrancheStatus.SCHEDULED,
                    InstallmentTrancheStatus.OVERDUE,
                ]),
                InstallmentTranche.due_date <= today,
            )
            .order_by(
                InstallmentTranche.plan_id.asc(),
                InstallmentTranche.number.asc(),
            )
        )
        result = await session.execute(stmt)
        due_rows = result.all()

    if not due_rows:
        return

    logger.info(
        "installment_batch_due_tranches",
        count=len(due_rows),
    )

    # Process each tranche in its own transaction.
    paid_count = 0
    overdue_count = 0
    error_count = 0

    for row in due_rows:
        try:
            async with factory() as session:
                async with session.begin():
                    # Reload tranche and plan within this transaction.
                    tranche = await session.get(InstallmentTranche, row.id)
                    plan = await session.get(InstallmentPlan, row.plan_id)

                    if tranche is None or plan is None:
                        continue

                    # Skip if plan is no longer active.
                    if plan.status != InstallmentPlanStatus.ACTIVE:
                        continue

                    # Skip if tranche already paid/cancelled/defaulted.
                    if tranche.status not in (
                        InstallmentTrancheStatus.SCHEDULED,
                        InstallmentTrancheStatus.OVERDUE,
                    ):
                        continue

                    was_paid = await pay_tranche(tranche, plan, session)

                    if was_paid:
                        paid_count += 1
                    else:
                        overdue_count += 1

        except Exception:
            error_count += 1
            logger.exception(
                "installment_tranche_processing_error",
                tranche_id=str(row.id),
                plan_id=str(row.plan_id),
            )

    logger.info(
        "installment_batch_due_completed",
        paid=paid_count,
        overdue=overdue_count,
        errors=error_count,
    )


async def _process_defaults(today: date) -> None:
    """Find overdue tranches past the grace period and default their plans."""
    factory = get_session_factory()
    default_cutoff = today - timedelta(days=settings.installment_default_days)

    # Find overdue tranches past the grace period.
    async with factory() as session:
        stmt = (
            select(InstallmentTranche.id, InstallmentTranche.plan_id)
            .where(
                InstallmentTranche.status == InstallmentTrancheStatus.OVERDUE,
                InstallmentTranche.due_date <= default_cutoff,
            )
            .order_by(InstallmentTranche.plan_id.asc())
        )
        result = await session.execute(stmt)
        default_rows = result.all()

    if not default_rows:
        return

    logger.info(
        "installment_batch_defaults",
        count=len(default_rows),
    )

    # Process each default in its own transaction.
    default_count = 0
    error_count = 0

    # Deduplicate by plan_id (multiple overdue tranches may exist per plan).
    seen_plans: set[str] = set()

    for row in default_rows:
        plan_id_str = str(row.plan_id)
        if plan_id_str in seen_plans:
            continue
        seen_plans.add(plan_id_str)

        try:
            async with factory() as session:
                async with session.begin():
                    tranche = await session.get(InstallmentTranche, row.id)
                    plan = await session.get(InstallmentPlan, row.plan_id)

                    if tranche is None or plan is None:
                        continue

                    # Skip if plan already defaulted/completed/cancelled.
                    if plan.status != InstallmentPlanStatus.ACTIVE:
                        continue

                    await default_plan(plan, tranche, session)
                    default_count += 1

        except Exception:
            error_count += 1
            logger.exception(
                "installment_default_processing_error",
                tranche_id=str(row.id),
                plan_id=str(row.plan_id),
            )

    logger.info(
        "installment_batch_defaults_completed",
        defaulted=default_count,
        errors=error_count,
    )
