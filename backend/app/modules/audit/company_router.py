# =============================================================================
# AIVIS.ONE Backend -- Company Self-Service Audit Feed Router (TASK-39 item 7)
# =============================================================================
#
# ENDPOINT:
#   GET /api/v1/company/audit -- paginated, newest-first feed of the
#                                 CALLER'S OWN company (project) write
#                                 history.
#
# THE GAP THIS CLOSES: audit/router.py's GET /api/v1/staff/audit/companies
# already lets STAFF read a project's write history (who changed what,
# when). Nothing let the project itself see the same history for its
# own project. audit/service.py::list_company_audit_feed() already
# accepts a company_id filter -- this endpoint is that exact same
# query, with company_id taken from get_current_company_profile()
# (companies/dependencies.py) and NEVER from client input. There is
# deliberately NO company_id (or any other company-selecting) query
# parameter on this route -- a company must never be able to ask for
# another project's history. The dependency alone decides whose feed
# this is.
#
# RESPONSE SHAPE: CompanySelfAuditEntryResponse (audit/schemas.py) --
# a DELIBERATELY NARROWER schema than the staff-facing
# CompanyAuditEntryResponse. It carries id / event / created_at /
# actor_type / changed_fields ONLY -- no actor_id, no performed_by, no
# on_behalf_of (a company must never learn WHICH staff member made a
# change), and no raw `data` (would leak values -- see
# CompanySelfAuditEntryResponse / _derive_changed_fields() in
# schemas.py for the full reasoning, including why
# company.price_updated rows carry an empty changed_fields list).
# CompanyAuditEntryResponse / CompanyAuditFeedResponse (the staff
# schemas) must NEVER be reused on this route.
#
# SCOPE NOTE (inherited from audit/service.py's own header, unchanged
# here): this feed filters strictly on target_type="company". Writes
# recorded under target_type="roadmap_item" / "attachment" (the
# STAFF-driven sub-entity write paths in companies/service.py) will
# NOT appear here -- only rows keyed directly to the company's own id,
# which is what every project self-service write in companies/
# service.py already uses. Not something this delivery changes or
# should change.
#
# EVENT SCOPE: filtered to events named "company.*" (event_prefix on
# list_company_audit_feed, default None so the staff feed is unchanged).
# target_type="company" alone is NOT sufficient -- purchase.
# template_missing is a system-written error row keyed to the company
# that would otherwise appear here. See the service docstring.
#
# READ-ONLY, NO MUTATION AFFORDANCE OF ANY KIND -- same TASK-30 ruling
# audit/router.py's header documents (approve/reject/acknowledge/
# pending were explicitly ruled out for this whole feed concept, twice).
# This is a plain GET over immutable AuditLog rows.
#
# AVATAR GUARD: deliberately NOT applied. forbid_avatar()
# (auth/avatar_guard.py) only gates the RESTRICTED_OPERATIONS set --
# actions that move money/identity or whose effect persists past the
# avatar session (see that module's header for the full list and
# reasoning). This route is a plain read (GET, get_db_reader, no state
# change of any kind) -- the same category avatar_guard.py's own
# header explicitly leaves UNGUARDED for GET /sessions and GET
# /preferences ("read-only visibility, the same category of access
# avatar mode already grants over the target's other data"). Nothing
# about this endpoint fits the guard's own stated test, so none is
# added here.
#
# COMMIT RULE (P-01): read-only, uses get_db_reader.
# =============================================================================

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.modules.audit.schemas import (
    CompanySelfAuditEntryResponse,
    CompanySelfAuditFeedResponse,
)
from app.modules.audit.service import list_company_audit_feed
from app.modules.companies.dependencies import get_current_company_profile
from app.modules.companies.models import CompanyProfile

router = APIRouter(prefix="/api/v1/company/audit", tags=["company-audit"])


@router.get(
    "",
    response_model=CompanySelfAuditFeedResponse,
)
async def list_own_audit_feed_endpoint(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_reader),
) -> CompanySelfAuditFeedResponse:
    """The caller's own company (project) write history, newest-first.

    company_id is FORCED to the authenticated caller's own
    CompanyProfile.id -- there is no company_id parameter on this
    route for a client to override, unlike the staff equivalent.
    """
    entries, total = await list_company_audit_feed(
        session,
        company_id=company.id,
        # Only rows describing a change TO this project. A row can be
        # keyed to a company without being a write to it: purchases/
        # engine.py records "purchase.template_missing" (actor_type=
        # "system") against the company beside a logger.error() when a
        # document template is missing. Staff see that in their feed
        # and should; showing a customer our own internal error under
        # "what changed on my project" would be both confusing and a
        # needless disclosure of an operational failure.
        event_prefix="company.",
        page=page,
        per_page=per_page,
    )
    return CompanySelfAuditFeedResponse(
        items=[CompanySelfAuditEntryResponse.from_entry(e) for e in entries],
        total=total,
        page=page,
        per_page=per_page,
    )
