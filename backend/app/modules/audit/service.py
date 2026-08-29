# =============================================================================
# AIVIS.ONE Backend -- Company Audit Feed Service (TASK-30 ruling 3 / F2)
# =============================================================================
#
# NOT NEW AUDIT INFRASTRUCTURE. app.core.audit.AuditLog (table
# audit_log, already migrated in initial_schema.py) and record_audit()
# already ARE this codebase's "who did what to what, when" mechanism --
# used from ~15 other modules, including companies/service.py's
# create_company / update_company / assign_company, which already
# write target_type="company", target_id=<company_profiles.id> on
# every staff-driven company write. F1 (who + when on every write) is
# therefore already satisfied structurally: a future project
# self-service write endpoint just calls record_audit(session,
# target_type="company", target_id=company_id, event="company.
# <field>_updated", actor_id=..., actor_type=..., data=...) the same
# way create_company already does -- a one-line addition per endpoint,
# not new infrastructure.
#
# WHAT THIS MODULE ACTUALLY ADDS is F2, the genuine gap: nothing in
# this codebase reads AuditLog back out yet (confirmed by grep -- the
# model is only referenced from core/audit.py, core/mixins.py,
# core/constants.py, core/middleware.py, and migrations/env.py; no
# router anywhere queries it). list_company_audit_feed() is that
# read -- a plain, read-only, paginated, date-filterable SELECT over
# rows other code already writes.
#
# SCOPE NOTE ON target_type: this feed filters strictly on
# target_type="company", target_id=company_profiles.id -- the exact
# discriminator create_company/update_company/assign_company already
# use. Sub-entity writes that follow the OTHER existing target_type
# conventions in companies/service.py (target_type="roadmap_item" /
# target_id=<roadmap item id>, target_type="attachment" /
# target_id=<attachment id>) will NOT appear in this feed even when
# company-scoped, because their target_id is the sub-entity's own id,
# not the company's. That is an existing characteristic of AuditLog's
# polymorphic target_type/target_id design, inherited as-is here, not
# something this delivery changes -- flagged for whoever builds the
# roadmap-editing / attachment-upload self-service write paths next,
# since they will need to decide whether to key those events to the
# sub-entity (matching today's staff-driven convention) or to the
# company (so they show up here too).
#
# COMMIT RULE (P-01): read-only. Never commits, never writes.
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog

# The discriminator already used by companies/service.py's own
# record_audit() calls (create_company, update_company, assign_company,
# ...). Kept as a module constant rather than a caller-supplied
# parameter -- this feed is specifically the company-write feed, not a
# generic AuditLog browser.
_TARGET_TYPE = "company"


async def list_company_audit_feed(
    session: AsyncSession,
    *,
    company_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    event_prefix: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[AuditLog], int]:
    """Paginated, filtered feed of company (project) writes (F2).

    Staff-facing read-only history -- see
    app/modules/audit/router.py. Newest-first, same pagination
    contract as list_companies / list_price_history /
    list_transactions elsewhere in this codebase.

    THIS IS A RECORD, NOT A QUEUE: a plain filtered SELECT over rows
    record_audit() already wrote. Nothing here can be actioned,
    approved, dismissed, or otherwise mutated -- TASK-30 explicitly
    ruled out a moderation/approval queue for this ruling.

    Args:
        session: Read-only session is sufficient -- no writes here.
        company_id: Optional exact-match filter on target_id -- one
            project's full write history.
        date_from: Inclusive lower bound on created_at.
        date_to: Inclusive upper bound on created_at.
        event_prefix: Optional prefix the event name must start with.
            DEFAULT None keeps the staff feed exactly as it was --
            every row of every event. The company self-service feed
            (audit/company_router.py) passes "company." so that rows
            which are keyed to a company but are NOT a write to it
            never reach the project itself. The live case is
            purchases/engine.py's "purchase.template_missing", an
            actor_type="system" row written beside a logger.error()
            when a document template is missing: it targets the
            company, so it lands in this feed's target_type filter,
            but it is an internal platform failure rather than a
            change anyone made to the project. Staff should see it;
            a customer reading "what changed on my project" should
            not be shown our own error log.
        page, per_page: Standard pagination.

    Returns:
        (entries, total_count) tuple.
    """
    conditions = [AuditLog.target_type == _TARGET_TYPE]
    if company_id is not None:
        conditions.append(AuditLog.target_id == company_id)
    if date_from is not None:
        conditions.append(AuditLog.created_at >= date_from)
    if date_to is not None:
        conditions.append(AuditLog.created_at <= date_to)
    if event_prefix is not None:
        conditions.append(AuditLog.event.startswith(event_prefix))

    count_stmt = select(func.count()).select_from(AuditLog).where(*conditions)
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(AuditLog)
        .where(*conditions)
        # created_at ALONE IS NOT A STABLE SORT HERE. It defaults to
        # func.now(), which in PostgreSQL is TRANSACTION start time --
        # frozen across every statement in the transaction. record_audit()
        # flushes without committing (P-01), so a request that records
        # several company rows gives them all an IDENTICAL created_at.
        # With ties and no tiebreaker, SQL does not promise the same
        # order for two separate SELECTs, so a row could appear on both
        # page 1 and page 2, or on neither. id breaks the tie
        # deterministically -- the same fix commissions/service.py
        # already applies to its own ledger feed.
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    entries = list(result.scalars().all())

    return entries, total
