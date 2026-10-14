# =============================================================================
# AIVIS.ONE Backend -- Installment Worker (Sprint 6.2, fix TD-042)
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
#
# TD-042 FIX:
#   session.get() replaced with SELECT ... FOR UPDATE to serialize
#   concurrent worker instances (prevents double-payment / double-default).
#
# KYC PAUSE (H34 P-126, owner's decision 2026-10-14):
#   A plan whose owner's kyc_status is not APPROVED is PAUSED. The daemon
#   neither pays its tranche (paying turns a balance into ownership --
#   exactly what kyc/gate.py closes to an unverified person), nor moves it
#   into OVERDUE, nor defaults the plan; it logs the skip and leaves every
#   row as it found it. Back in APPROVED, the next pass treats the plan as
#   if nothing had happened: a SCHEDULED tranche whose due date passed
#   during the pause is due and is paid, or goes OVERDUE on a short
#   balance, like any other.
#
#   One predicate, _owner_kyc_paused, guards BOTH phases, and it is the
#   only place this rule lives. It is not inside pay_tranche: create_plan
#   calls pay_tranche for the first tranche behind its own KYC refusal,
#   and pay_tranche's bool answers "paid or overdue" -- a third outcome
#   would change its contract for that caller too. Nor inside
#   default_plan, which would leave phase 1 free to push a paused tranche
#   into OVERDUE and start its default clock.
# =============================================================================

from datetime import date, datetime, timedelta, UTC

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session_factory
from app.modules.installments.constants import (
    InstallmentPlanStatus,
    InstallmentTrancheStatus,
)
from app.modules.installments.models import InstallmentPlan, InstallmentTranche
from app.modules.installments.service import default_plan, pay_tranche
from app.modules.users.models import KYCStatus, User

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


async def _load_tranche_for_update(
    session: AsyncSession,
    tranche_id,
) -> InstallmentTranche | None:
    """Load tranche with FOR UPDATE lock."""
    stmt = (
        select(InstallmentTranche)
        .where(InstallmentTranche.id == tranche_id)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _load_plan_for_update(
    session: AsyncSession,
    plan_id,
) -> InstallmentPlan | None:
    """Load plan with FOR UPDATE lock."""
    stmt = (
        select(InstallmentPlan)
        .where(InstallmentPlan.id == plan_id)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _owner_kyc_paused(
    session: AsyncSession,
    plan: InstallmentPlan,
) -> bool:
    """True when the plan's owner is not KYC-APPROVED -- the plan is paused.

    TAKES THE PER-PERSON LOCK FIRST, on the key submit_kyc, decide_by_user,
    decide_by_application and engine.execute take. Without it a revocation
    committed between this read and the lock engine.execute takes inside
    pay_tranche would still let the tranche through: the read would have
    said APPROVED a moment before it stopped being true. Under the lock the
    status cannot change until this transaction ends, and engine.execute
    re-taking the same transaction-level lock later succeeds at once
    (advisory locks are re-entrant within one session).

    Lock order is unchanged by this: the caller already holds the tranche
    and plan row locks, and the payment path already took the advisory lock
    after them (inside engine.execute) before this function existed.

    The status is read as a bare COLUMN, not as a User entity: an entity
    already in the identity map would come back with its cached status.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": plan.investor_id.int & 0x7FFFFFFFFFFFFFFF},
    )
    result = await session.execute(
        select(User.kyc_status).where(User.id == plan.investor_id)
    )
    # scalar_one: investor_id is a NOT NULL foreign key with
    # ondelete=RESTRICT, so the owner row exists for every plan.
    kyc_status = result.scalar_one()
    if kyc_status == KYCStatus.APPROVED:
        return False

    logger.info(
        "installment_plan_paused_kyc",
        plan_id=str(plan.id),
        investor_id=str(plan.investor_id),
        kyc_status=kyc_status,
    )
    return True


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
    paused_count = 0
    error_count = 0

    for row in due_rows:
        try:
            async with factory() as session:
                async with session.begin():
                    # Reload tranche and plan with FOR UPDATE (TD-042).
                    tranche = await _load_tranche_for_update(session, row.id)
                    plan = await _load_plan_for_update(session, row.plan_id)

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

                    # H34 P-126: neither paid nor marked OVERDUE.
                    if await _owner_kyc_paused(session, plan):
                        paused_count += 1
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
        paused=paused_count,
        errors=error_count,
    )


async def _process_defaults(today: date) -> None:
    """Find overdue tranches past the grace period and default their plans.

    KNOWN CEILING -- a pause does not extend the grace period.
      1. Mechanism: the grace window is counted from the tranche's
         due_date (default_cutoff below); nothing records when a pause
         began or ended. A plan paused for longer than
         INSTALLMENT_DEFAULT_DAYS comes back from re-approval with its
         window already spent: if the balance is short on the first pass
         after re-approval, phase 1 moves the tranche to OVERDUE and phase
         2 of the SAME pass defaults the plan, with no day of grace. A
         tranche that was already OVERDUE before the pause loses the
         paused days from its window the same way.
      2. Status: acknowledged by design (H34, owner's decision).
      3. Task: none -- there are no users yet whom it could reach.
      4. Trigger: the first plan that stays paused longer than
         INSTALLMENT_DEFAULT_DAYS (visible as installment_plan_paused_kyc
         log lines for the same plan_id spanning more days than that).
      5. Agreed fix: count the window from the end of the pause -- needs a
         column on the plan (or tranche) recording it, and a migration.
      6. Rejected: counting from the time of the owner's last KYC
         approval -- users does not store it.
    The pause itself is not a ceiling; see the module header.
    """
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
    paused_count = 0
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
                    # Reload with FOR UPDATE (TD-042).
                    tranche = await _load_tranche_for_update(session, row.id)
                    plan = await _load_plan_for_update(session, row.plan_id)

                    if tranche is None or plan is None:
                        continue

                    # Skip if plan already defaulted/completed/cancelled.
                    if plan.status != InstallmentPlanStatus.ACTIVE:
                        continue

                    # H34 P-126: a paused plan is not defaulted.
                    if await _owner_kyc_paused(session, plan):
                        paused_count += 1
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
        paused=paused_count,
        errors=error_count,
    )
