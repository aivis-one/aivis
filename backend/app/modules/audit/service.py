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

from sqlalchemy import func, select
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

    count_stmt = select(func.count()).select_from(AuditLog).where(*conditions)
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    entries = list(result.scalars().all())

    return entries, total
