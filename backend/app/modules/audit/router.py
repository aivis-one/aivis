# =============================================================================
# AIVIS.ONE Backend -- Company Audit Feed Router (TASK-30 ruling 3 / F2)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/staff/audit/companies -- paginated, date-filterable
#                                         feed of company (project)
#                                         writes recorded via
#                                         record_audit()
#
# PERMISSION:
#   project_manage -- the key TASK-30 SS7 ruling 6/8 already narrowed
#   onto project-management write routes (companies, pools, products,
#   company attachments -- see staff/constants.py, backfilled onto
#   pre-existing admins by migration 2026_08_26_0043). Reading the
#   record of what projects wrote to themselves is a project-
#   management concern in the same sense those writes are, so it is
#   gated on the same key rather than company_manage (the broader
#   staff-CRUD-on-companies permission) or a new key.
#
# READ-ONLY, NO MUTATION AFFORDANCES OF ANY KIND. TASK-30 explicitly
# ruled OUT a moderation/approval queue for this ruling -- twice, the
# second time calling it "not needed even as a task". This is a plain
# GET over immutable AuditLog rows: no approve, reject, acknowledge,
# or pending state exists anywhere in this module, and none should be
# added here. Writes already applied immediately, before this endpoint
# ever sees them; this is after-the-fact visibility only.
#
# COMMIT RULE (P-01): read-only, uses get_db_reader.
# =============================================================================

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.modules.audit.schemas import (
    CompanyAuditEntryResponse,
    CompanyAuditFeedResponse,
)
from app.modules.audit.service import list_company_audit_feed
from app.modules.auth.dependencies import require_staff_permission
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/staff/audit", tags=["staff-audit"])


@router.get(
    "/companies",
    response_model=CompanyAuditFeedResponse,
)
async def list_company_audit_feed_endpoint(
    company_id: UUID | None = Query(
        default=None,
        description="Filter to one project's full write history.",
    ),
    date_from: datetime | None = Query(
        default=None, description="Inclusive lower bound on created_at."
    ),
    date_to: datetime | None = Query(
        default=None, description="Inclusive upper bound on created_at."
    ),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    staff: User = Depends(require_staff_permission("project_manage")),
    session: AsyncSession = Depends(get_db_reader),
) -> CompanyAuditFeedResponse:
    """Admin feed of what projects changed over a period (F2).

    Newest-first. A plain filtered read over AuditLog rows written by
    record_audit() with target_type="company" -- no approval, no
    pending state, nothing to action here.
    """
    entries, total = await list_company_audit_feed(
        session,
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )
    return CompanyAuditFeedResponse(
        items=[CompanyAuditEntryResponse.model_validate(e) for e in entries],
        total=total,
        page=page,
        per_page=per_page,
    )
