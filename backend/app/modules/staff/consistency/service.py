# =============================================================================
# CBSHOME Backend -- Consistency Semaphore Service (Sprint 6.4)
# =============================================================================
#
# RESPONSIBILITIES:
#   run_all()   -- execute all 19 semaphores, return aggregated results
#   s_01..s_13  -- core financial consistency checks
#   is_01..is_06 -- installment-specific checks
#
# Each semaphore is an independent async function that queries the DB
# and returns a SemaphoreResult. All checks are read-only.
#
# FAILURES:
#   On fail, record_audit() logs the failure with details.
#   structlog ALERT for critical failures.
#
# SEMAPHORE REFERENCE: CBSHOME-Financial-System.md section 12,
#   CBSHOME-Installment.md section 8.
# =============================================================================

from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.modules.staff.consistency.schemas import SemaphoreResult
from app.modules.installments.constants import (
    InstallmentPlanStatus,
    InstallmentTrancheStatus,
)
from app.modules.installments.models import InstallmentPlan, InstallmentTranche
from app.modules.ledgers.models import ActiveLedger, LedgerStatus, PassiveLedger
from app.modules.payments.constants import PaymentStatus
from app.modules.payments.models import Payment
from app.modules.purchases.models import Purchase
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()


def _safe_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert Decimal values to int for JSON serialization.

    func.sum() on BigInteger returns Decimal which is not JSON-serializable.
    """
    if details is None:
        return None
    return {
        k: int(v) if isinstance(v, Decimal) else v
        for k, v in details.items()
    }


def _result(
    name: str,
    severity: str,
    passed: bool,
    details: dict[str, Any] | None = None,
) -> SemaphoreResult:
    """Build a SemaphoreResult."""
    return SemaphoreResult(
        name=name,
        status="pass" if passed else "fail",
        severity=severity,
        details=_safe_details(details),
    )


# ---------------------------------------------------------------------------
# Core semaphores (S-01 .. S-13, skipping S-07)
# ---------------------------------------------------------------------------


async def s_01(session: AsyncSession) -> SemaphoreResult:
    """S-01: SUM(all ledger entries including reversed) = 0."""
    active_sum_stmt = select(
        func.coalesce(func.sum(ActiveLedger.amount_cents), 0)
    )
    passive_sum_stmt = select(
        func.coalesce(func.sum(PassiveLedger.amount_cents), 0)
    )
    active_sum = (await session.execute(active_sum_stmt)).scalar_one()
    passive_sum = (await session.execute(passive_sum_stmt)).scalar_one()
    total = active_sum + passive_sum
    return _result(
        "S-01", "critical", total == 0,
        {"active_sum": active_sum, "passive_sum": passive_sum, "total": total},
    )


async def s_02(session: AsyncSession) -> SemaphoreResult:
    """S-02: Each Purchase has exactly one active_ledger entry.

    COUNT(active_ledger with purchase/gift reasons) = COUNT(purchases).
    """
    purchase_count_stmt = select(func.count()).select_from(Purchase)
    purchase_count = (await session.execute(purchase_count_stmt)).scalar_one()

    # Active ledger entries linked to purchases via reason prefix.
    ledger_count_stmt = select(func.count()).select_from(ActiveLedger).where(
        ActiveLedger.reason.like("purchase:%")
        | ActiveLedger.reason.like("gift:%")
        | ActiveLedger.reason.like("installment:tranche:%")
    )
    ledger_count = (await session.execute(ledger_count_stmt)).scalar_one()

    return _result(
        "S-02", "critical", purchase_count == ledger_count,
        {"purchase_count": purchase_count, "ledger_count": ledger_count},
    )


async def s_03(session: AsyncSession) -> SemaphoreResult:
    """S-03: SUM(paid_cents) = ABS(SUM(active debits by purchases))."""
    paid_stmt = select(
        func.coalesce(func.sum(Purchase.paid_cents), 0)
    )
    paid_total = (await session.execute(paid_stmt)).scalar_one()

    debit_stmt = select(
        func.coalesce(func.sum(ActiveLedger.amount_cents), 0)
    ).where(ActiveLedger.reason.like("purchase:%"))
    debit_total = (await session.execute(debit_stmt)).scalar_one()

    return _result(
        "S-03", "critical", paid_total == abs(debit_total),
        {"paid_cents_total": paid_total, "active_debit_total": debit_total},
    )


async def s_04(session: AsyncSession) -> SemaphoreResult:
    """S-04: No active_ledger entries for users with role=company."""
    stmt = (
        select(func.count())
        .select_from(ActiveLedger)
        .join(User, ActiveLedger.user_id == User.id)
        .where(User.role == UserRole.COMPANY)
    )
    count = (await session.execute(stmt)).scalar_one()
    return _result(
        "S-04", "critical", count == 0,
        {"company_active_ledger_count": count},
    )


async def s_05(session: AsyncSession) -> SemaphoreResult:
    """S-05: No users with confirmed active_balance < 0."""
    stmt = (
        select(func.count())
        .select_from(
            select(
                ActiveLedger.user_id,
                func.sum(ActiveLedger.amount_cents).label("balance"),
            )
            .where(ActiveLedger.status == LedgerStatus.CONFIRMED)
            .group_by(ActiveLedger.user_id)
            .having(func.sum(ActiveLedger.amount_cents) < 0)
            .subquery()
        )
    )
    count = (await session.execute(stmt)).scalar_one()
    return _result(
        "S-05", "critical", count == 0,
        {"users_with_negative_active": count},
    )


async def s_06(session: AsyncSession) -> SemaphoreResult:
    """S-06: No users with confirmed passive_balance < 0."""
    stmt = (
        select(func.count())
        .select_from(
            select(
                PassiveLedger.user_id,
                func.sum(PassiveLedger.amount_cents).label("balance"),
            )
            .where(PassiveLedger.status == LedgerStatus.CONFIRMED)
            .group_by(PassiveLedger.user_id)
            .having(func.sum(PassiveLedger.amount_cents) < 0)
            .subquery()
        )
    )
    count = (await session.execute(stmt)).scalar_one()
    return _result(
        "S-06", "critical", count == 0,
        {"users_with_negative_passive": count},
    )


async def s_08(session: AsyncSession) -> SemaphoreResult:
    """S-08: No confirmed entries with origin_payment_id of reversed Payment."""
    # Active ledger.
    active_stmt = (
        select(func.count())
        .select_from(ActiveLedger)
        .join(Payment, ActiveLedger.origin_payment_id == Payment.id)
        .where(
            ActiveLedger.status == LedgerStatus.CONFIRMED,
            Payment.status == PaymentStatus.REVERSED,
        )
    )
    active_count = (await session.execute(active_stmt)).scalar_one()

    # Passive ledger.
    passive_stmt = (
        select(func.count())
        .select_from(PassiveLedger)
        .join(Payment, PassiveLedger.origin_payment_id == Payment.id)
        .where(
            PassiveLedger.status == LedgerStatus.CONFIRMED,
            Payment.status == PaymentStatus.REVERSED,
        )
    )
    passive_count = (await session.execute(passive_stmt)).scalar_one()

    total = active_count + passive_count
    return _result(
        "S-08", "critical", total == 0,
        {"active_orphans": active_count, "passive_orphans": passive_count},
    )


async def s_09(session: AsyncSession) -> SemaphoreResult:
    """S-09: Each :reversal entry has a corresponding original with status=reversed."""
    # Active reversal entries without reversed original.
    active_stmt = (
        select(func.count())
        .select_from(ActiveLedger)
        .where(ActiveLedger.reason.like("%:reversal"))
    )
    active_reversals = (await session.execute(active_stmt)).scalar_one()

    active_originals_stmt = (
        select(func.count())
        .select_from(ActiveLedger)
        .where(
            ActiveLedger.status == LedgerStatus.REVERSED,
            ~ActiveLedger.reason.like("%:reversal"),
        )
    )
    active_originals = (await session.execute(active_originals_stmt)).scalar_one()

    # Passive reversal entries.
    passive_stmt = (
        select(func.count())
        .select_from(PassiveLedger)
        .where(PassiveLedger.reason.like("%:reversal"))
    )
    passive_reversals = (await session.execute(passive_stmt)).scalar_one()

    passive_originals_stmt = (
        select(func.count())
        .select_from(PassiveLedger)
        .where(
            PassiveLedger.status == LedgerStatus.REVERSED,
            ~PassiveLedger.reason.like("%:reversal"),
        )
    )
    passive_originals = (await session.execute(passive_originals_stmt)).scalar_one()

    passed = (
        active_reversals == active_originals
        and passive_reversals == passive_originals
    )
    return _result(
        "S-09", "high", passed,
        {
            "active_reversals": active_reversals,
            "active_originals_reversed": active_originals,
            "passive_reversals": passive_reversals,
            "passive_originals_reversed": passive_originals,
        },
    )


async def s_10(session: AsyncSession) -> SemaphoreResult:
    """S-10 / IS-01: SUM(tranches.amount_cents) = plan.total_price_cents for each plan."""
    stmt = (
        select(func.count())
        .select_from(
            select(
                InstallmentPlan.id,
                InstallmentPlan.total_price_cents,
                func.sum(InstallmentTranche.amount_cents).label("tranche_sum"),
            )
            .join(
                InstallmentTranche,
                InstallmentTranche.plan_id == InstallmentPlan.id,
            )
            .group_by(InstallmentPlan.id, InstallmentPlan.total_price_cents)
            .having(
                func.sum(InstallmentTranche.amount_cents)
                != InstallmentPlan.total_price_cents
            )
            .subquery()
        )
    )
    count = (await session.execute(stmt)).scalar_one()
    return _result(
        "S-10", "critical", count == 0,
        {"mismatched_plans": count},
    )


async def s_11(session: AsyncSession) -> SemaphoreResult:
    """S-11: Platform passive_ledger (confirmed) balance >= 0."""
    platform_stmt = select(User.id).where(User.role == UserRole.PLATFORM)
    platform_result = await session.execute(platform_stmt)
    platform_user = platform_result.scalar_one_or_none()

    if platform_user is None:
        return _result("S-11", "high", False, {"error": "Platform user not found"})

    balance_stmt = select(
        func.coalesce(func.sum(PassiveLedger.amount_cents), 0)
    ).where(
        PassiveLedger.user_id == platform_user,
        PassiveLedger.status == LedgerStatus.CONFIRMED,
    )
    balance = (await session.execute(balance_stmt)).scalar_one()

    return _result(
        "S-11", "high", balance >= 0,
        {"platform_passive_confirmed": balance},
    )


async def s_12(session: AsyncSession) -> SemaphoreResult:
    """S-12: All Purchase(gift) have paid_cents = 0."""
    stmt = (
        select(func.count())
        .select_from(Purchase)
        .where(Purchase.legal_basis == "gift", Purchase.paid_cents != 0)
    )
    count = (await session.execute(stmt)).scalar_one()
    return _result(
        "S-12", "high", count == 0,
        {"gift_purchases_with_nonzero_paid": count},
    )


async def s_13(session: AsyncSession) -> SemaphoreResult:
    """S-13: SUM(purchases.units) by company matches expectations.

    Checks that total units from sale+gift purchases are non-negative
    per company (basic sanity -- full cross-check requires unit tracking).
    """
    stmt = (
        select(func.count())
        .select_from(
            select(
                Purchase.company_id,
                func.sum(Purchase.units).label("total_units"),
            )
            .where(Purchase.status == "active")
            .group_by(Purchase.company_id)
            .having(func.sum(Purchase.units) < 0)
            .subquery()
        )
    )
    count = (await session.execute(stmt)).scalar_one()
    return _result(
        "S-13", "high", count == 0,
        {"companies_with_negative_units": count},
    )


# ---------------------------------------------------------------------------
# Installment semaphores (IS-01 .. IS-06)
# ---------------------------------------------------------------------------


async def is_01(session: AsyncSession) -> SemaphoreResult:
    """IS-01: SUM(tranches.amount_cents) = plan.total_price_cents (alias of S-10)."""
    result = await s_10(session)
    return _result("IS-01", "critical", result.status == "pass", result.details)


async def is_02(session: AsyncSession) -> SemaphoreResult:
    """IS-02: For completed plans, SUM(units_unlocked of paid tranches) + bonus = total_units."""
    # Get completed plans with their total_units and snapshot bonus_units.
    plans_stmt = (
        select(InstallmentPlan)
        .where(InstallmentPlan.status == InstallmentPlanStatus.COMPLETED)
    )
    plans_result = await session.execute(plans_stmt)
    plans = list(plans_result.scalars().all())

    mismatched = 0
    for plan in plans:
        # Sum units_unlocked from paid tranches.
        units_stmt = select(
            func.coalesce(func.sum(InstallmentTranche.units_unlocked), 0)
        ).where(
            InstallmentTranche.plan_id == plan.id,
            InstallmentTranche.status == InstallmentTrancheStatus.PAID,
        )
        paid_units = (await session.execute(units_stmt)).scalar_one()

        bonus = plan.plan_config_snapshot.get("bonus_units", 0)

        if paid_units + bonus != plan.total_units:
            mismatched += 1

    return _result(
        "IS-02", "critical", mismatched == 0,
        {"completed_plans_checked": len(plans), "mismatched": mismatched},
    )


async def is_03(session: AsyncSession) -> SemaphoreResult:
    """IS-03: No scheduled tranches for defaulted/cancelled plans."""
    stmt = (
        select(func.count())
        .select_from(InstallmentTranche)
        .join(
            InstallmentPlan,
            InstallmentTranche.plan_id == InstallmentPlan.id,
        )
        .where(
            InstallmentPlan.status.in_([
                InstallmentPlanStatus.DEFAULTED,
                InstallmentPlanStatus.CANCELLED,
            ]),
            InstallmentTranche.status == InstallmentTrancheStatus.SCHEDULED,
        )
    )
    count = (await session.execute(stmt)).scalar_one()
    return _result(
        "IS-03", "critical", count == 0,
        {"orphan_scheduled_tranches": count},
    )


async def is_04(session: AsyncSession) -> SemaphoreResult:
    """IS-04: Each paid tranche has purchase_id NOT NULL."""
    stmt = (
        select(func.count())
        .select_from(InstallmentTranche)
        .where(
            InstallmentTranche.status == InstallmentTrancheStatus.PAID,
            InstallmentTranche.purchase_id.is_(None),
        )
    )
    count = (await session.execute(stmt)).scalar_one()
    return _result(
        "IS-04", "critical", count == 0,
        {"paid_tranches_without_purchase": count},
    )


async def is_05(session: AsyncSession) -> SemaphoreResult:
    """IS-05: COUNT(paid tranches) = COUNT(purchases with legal_basis=installment_tranche) per plan."""
    # Paid tranches per plan.
    paid_stmt = (
        select(
            InstallmentTranche.plan_id,
            func.count().label("paid_count"),
        )
        .where(InstallmentTranche.status == InstallmentTrancheStatus.PAID)
        .group_by(InstallmentTranche.plan_id)
    )
    paid_result = await session.execute(paid_stmt)
    paid_map: dict = {row.plan_id: row.paid_count for row in paid_result.all()}

    # Purchases with legal_basis=installment_tranche per plan.
    # Link via InstallmentTranche.purchase_id -> Purchase.id.
    purchase_stmt = (
        select(
            InstallmentTranche.plan_id,
            func.count().label("purchase_count"),
        )
        .join(Purchase, InstallmentTranche.purchase_id == Purchase.id)
        .where(
            Purchase.legal_basis == "installment_tranche",
            InstallmentTranche.status == InstallmentTrancheStatus.PAID,
        )
        .group_by(InstallmentTranche.plan_id)
    )
    purchase_result = await session.execute(purchase_stmt)
    purchase_map: dict = {
        row.plan_id: row.purchase_count for row in purchase_result.all()
    }

    mismatched = 0
    for plan_id, paid_count in paid_map.items():
        if purchase_map.get(plan_id, 0) != paid_count:
            mismatched += 1

    return _result(
        "IS-05", "high", mismatched == 0,
        {"plans_checked": len(paid_map), "mismatched": mismatched},
    )


async def is_06(session: AsyncSession) -> SemaphoreResult:
    """IS-06: No active plans where all tranches are paid (should be completed)."""
    # Active plans.
    active_plans_stmt = (
        select(InstallmentPlan.id)
        .where(InstallmentPlan.status == InstallmentPlanStatus.ACTIVE)
    )
    active_result = await session.execute(active_plans_stmt)
    active_plan_ids = [row[0] for row in active_result.all()]

    stuck = 0
    for plan_id in active_plan_ids:
        unpaid_stmt = (
            select(func.count())
            .select_from(InstallmentTranche)
            .where(
                InstallmentTranche.plan_id == plan_id,
                InstallmentTranche.status != InstallmentTrancheStatus.PAID,
            )
        )
        unpaid = (await session.execute(unpaid_stmt)).scalar_one()
        if unpaid == 0:
            stuck += 1

    return _result(
        "IS-06", "high", stuck == 0,
        {"active_plans_fully_paid": stuck},
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

# All semaphore functions in execution order.
_ALL_SEMAPHORES = [
    s_01, s_02, s_03, s_04, s_05, s_06,
    s_08, s_09, s_10, s_11, s_12, s_13,
    is_01, is_02, is_03, is_04, is_05, is_06,
]


async def run_all(
    session: AsyncSession,
    staff_id: Any = None,
) -> list[SemaphoreResult]:
    """Execute all consistency semaphores.

    Logs failures to audit_log and structlog.

    Args:
        session: Active DB session (read-only operations).
        staff_id: Staff user who triggered the check (for audit).

    Returns:
        List of SemaphoreResult for all semaphores.
    """
    results: list[SemaphoreResult] = []

    for semaphore_fn in _ALL_SEMAPHORES:
        try:
            result = await semaphore_fn(session)
        except Exception as exc:
            result = _result(
                semaphore_fn.__name__.upper().replace("_", "-"),
                "critical",
                False,
                {"error": str(exc)},
            )
            logger.exception(
                "semaphore_error",
                semaphore=result.name,
                error=str(exc),
            )

        results.append(result)

        # Log failures.
        if result.status == "fail":
            log_fn = (
                logger.critical if result.severity == "critical"
                else logger.warning
            )
            log_fn(
                "semaphore_failed",
                semaphore=result.name,
                severity=result.severity,
                details=result.details,
            )

            if staff_id is not None:
                await record_audit(
                    session=session,
                    event="consistency.semaphore_failed",
                    actor_id=staff_id,
                    actor_type="staff",
                    target_type="semaphore",
                    target_id=staff_id,
                    data={
                        "name": result.name,
                        "severity": result.severity,
                        "details": result.details,
                    },
                )

    return results
