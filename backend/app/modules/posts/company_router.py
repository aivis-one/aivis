# =============================================================================
# AIVIS.ONE Backend -- Posts Company Self-Service Router (TASK-30)
# =============================================================================
#
# ENDPOINTS:
#   GET    /api/v1/company/posts       -- list the caller's own posts
#                                          (drafts included, like staff)
#   POST   /api/v1/company/posts       -- create a post about the caller's
#                                          own company
#   PATCH  /api/v1/company/posts/{id}  -- update the caller's own post
#   DELETE /api/v1/company/posts/{id}  -- soft-delete the caller's own post
#
# RULING (TASK-30): project news is the project's own Post rows,
# owner_type="company", owner_id=<the company's own id>. No new entity,
# no schema change -- Post was already polymorphic (owner_type
# platform/company) before this delivery; this router is just the
# company-scoped write surface that did not exist yet. Mirrors the
# shape of staff_router.py's CRUD (same fields, same published_at
# transition, same soft delete) but every write is hard-scoped to the
# caller's OWN company_id, resolved server-side from the auth token via
# get_current_company_profile -- exactly the pattern GET /companies/me
# already uses (companies/router.py) and GET/POST /company/dashboard
# already uses for writes-adjacent reads (company_dashboard/router.py).
# There is no {company_id} in any of these URLs and none of the request
# schemas accept owner_type/owner_id/company_id -- a project can never
# create, edit, or delete a post for a different owner_id, because the
# id is never taken from client input in the first place. See
# posts/service.py's create_company_post/update_company_post/
# delete_company_post/_get_company_post_or_404 for the enforcement
# (cross-company and platform posts both 404, same as
# companies/attachments_router.py's isolation contract).
#
# is_banner is intentionally NOT exposed on this surface -- see
# CreateCompanyPostRequest's docstring in posts/schemas.py. Every
# company-authored post is created with is_banner=False; only staff
# (via /api/v1/staff/posts) can grant the site-wide homepage banner
# placement.
#
# MODERATION: none, by design. TASK-30 explicitly ruled out a
# moderation/approval queue for this feature (twice -- the second time
# "not needed even as a task"). A company's own post publishes the
# moment is_published=True is set, exactly like every other Post row;
# Post/Event carry no status/review-flag column beyond is_published +
# is_deleted, and this router does not add one.
#
# AUTH:
#   All endpoints require role=company via get_current_company_profile
#   (companies/dependencies.py), which 403s any caller without a
#   CompanyProfile (investor/agent/staff/platform).
#
# AUDIT:
#   record_audit(target_type="company", target_id=<own company_id>) on
#   every write -- see posts/service.py's "AUDIT DECISION" comment for
#   why target_type="company" was chosen over target_type="post" (so
#   these writes surface in GET /api/v1/staff/audit/companies).
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.companies.dependencies import get_current_company_profile
from app.modules.companies.models import CompanyProfile
from app.modules.posts.constants import OwnerType
from app.modules.posts.schemas import (
    CreateCompanyPostRequest,
    PostListResponse,
    PostResponse,
    UpdateCompanyPostRequest,
)
from app.modules.posts.service import (
    create_company_post,
    delete_company_post,
    staff_list_posts,
    update_company_post,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/company/posts", tags=["company-posts"])


@router.get(
    "",
    response_model=PostListResponse,
)
async def list_own_posts_endpoint(
    is_published: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_reader),
) -> PostListResponse:
    """List the caller's own company posts, drafts included.

    owner_type/owner_id are forced to "company" / the caller's own
    company_id -- there is no way to pass a different owner_id here,
    the endpoint takes none. Reuses staff_list_posts's query (same
    drafts-included behaviour, same search-escaping) with those two
    filters pinned, rather than duplicating the query logic.
    """
    rows, total = await staff_list_posts(
        session,
        owner_type=OwnerType.COMPANY.value,
        owner_id=company.id,
        is_published=is_published,
        search=search,
        page=page,
        per_page=per_page,
    )
    return PostListResponse(
        items=[PostResponse.model_validate(p) for p in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post(
    "",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_own_post_endpoint(
    body: CreateCompanyPostRequest,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> PostResponse:
    """Create a post about the caller's own company.

    Publishes immediately when is_published=True is passed -- no
    moderation/approval step (see module docstring).
    """
    post = await create_company_post(session, company.id, company.user_id, body)
    return PostResponse.model_validate(post)


@router.patch(
    "/{post_id}",
    response_model=PostResponse,
)
async def update_own_post_endpoint(
    post_id: UUID,
    body: UpdateCompanyPostRequest,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> PostResponse:
    """Partial update of the caller's own post.

    404s (never 403) if `post_id` belongs to a different company or to
    the platform -- see _get_company_post_or_404 in posts/service.py.
    """
    post = await update_company_post(
        session, company.id, post_id, company.user_id, body
    )
    return PostResponse.model_validate(post)


@router.delete(
    "/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_own_post_endpoint(
    post_id: UUID,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Soft-delete the caller's own post.

    404s (never 403) if `post_id` belongs to a different company or to
    the platform.
    """
    await delete_company_post(session, company.id, post_id, company.user_id)
