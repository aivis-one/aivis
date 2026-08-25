# =============================================================================
# AIVIS.ONE Backend -- Company Audit Feed Schemas (TASK-30 ruling 3 / F2)
# =============================================================================
#
# RESPONSE SCHEMAS:
#   CompanyAuditEntryResponse -- one AuditLog row (target_type="company")
#   CompanyAuditFeedResponse  -- paginated list, same envelope as
#                                CompanyListResponse / PriceHistoryListResponse
#                                / TransactionListResponse elsewhere in this
#                                codebase.
#
# Read-only surface. No request schema exists on purpose -- there is
# nothing here for a client to submit. Entries are written by
# record_audit() (app/core/audit.py), called directly from whichever
# service performs the write (create_company / update_company /
# assign_company today; future project self-service write endpoints
# the same way).
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanyAuditEntryResponse(BaseModel):
    """One company (project) write, as recorded by record_audit().

    `company_id` is AuditLog.target_id, renamed at the API boundary
    since target_type is constant ("company") for every row this feed
    returns and would add nothing by being surfaced.

    `actor_type` / `performed_by` / `on_behalf_of` are all exposed
    (rather than just actor_id) because the admin reading this feed
    needs to distinguish "the project account wrote this itself" from
    "a staff member wrote this on the project's behalf" -- including
    the avatar-mode case (Sprint 3.2: performed_by = staff acting,
    on_behalf_of = the identity they acted for), which record_audit()
    already auto-fills when the write happens inside an avatar
    session. Both are null for an ordinary (non-avatar) write.

    `data` defaults to {} rather than being Optional -- AuditLog.data
    is NOT NULL with a "{}" server_default, so the column is never
    actually null.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID = Field(validation_alias="target_id")
    event: str
    actor_id: UUID | None
    actor_type: str
    performed_by: UUID | None
    on_behalf_of: UUID | None
    data: dict  # type: ignore[type-arg]
    created_at: datetime


class CompanyAuditFeedResponse(BaseModel):
    """Paginated feed of company (project) writes (F2)."""

    items: list[CompanyAuditEntryResponse]
    total: int
    page: int
    per_page: int
