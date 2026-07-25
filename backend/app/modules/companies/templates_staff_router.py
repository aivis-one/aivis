# =============================================================================
# CBSHOME Backend -- Company Templates Staff Router (Refactor 2 iter 2.3)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/staff/companies/{company_id}/templates
#       ?kind=&language=&status=
#       -> list[TemplateResponse]                                       (200)
#
#       Per-company rows merged with platform-default `active` rows for
#       any (kind, language) pair the company hasn't covered with its
#       own active row. Surfaces "what the renderer would actually use"
#       so staff sees both the company's overrides AND the fallbacks.
#       See list_templates() in service.py for the merge logic.
#
#   GET /api/v1/staff/companies/{company_id}/templates/{template_id}
#       -> TemplateDetailResponse                                       (200)
#
#       Single template with HTML body inlined for inspection. The body
#       is read from MinIO via get_template_html_cached() so the staff
#       inspect path warms (and benefits from) the same Redis cache the
#       renderer uses. Platform-default rows are reachable here too --
#       a staff member legitimately needs to inspect the fallback that
#       a particular company is currently rendering through.
#
# AUTH:
#   Both endpoints require `company_manage` (R2 §4.6). No financial-ops
#   gate -- editing a template is content work, not a financial op. The
#   guarded transition (financial_operations) is the moment a Purchase
#   reaches the renderer, not the moment the template is uploaded.
#
# READ-ONLY in MVP (R2 §4.5):
#   No POST / PATCH / DELETE in this iteration. Template upload happens
#   through MinIO Web UI + `aivis storage reconcile-templates` (R2
#   §4.8). The full UI editor + multipart POST are post-MVP and will
#   take the same TemplateInboxMetadata schema as the inbox flow, so
#   any future router additions are additive on top of this surface.
#
# STORAGE FAILURES on the detail endpoint:
#   get_template_html_cached() can raise StorageNotFoundError if the
#   template.html object went missing (broken inventory) or StorageError
#   if the bucket itself is unavailable. Both are infrastructure faults
#   rather than client errors -- we let them propagate to FastAPI's
#   default 500 handler. A "broken template" surfaced as 500 to staff
#   matches the renderer's own 500 contract (R2 §4.7) and makes the
#   broken row visible enough to fix via reconcile.
#
# COMMIT RULE (P-01):
#   Read-only endpoints, get_db_reader. No commits.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.modules.auth.dependencies import require_staff_permission
from app.modules.companies.constants import (
    DocumentTemplateKind,
    TemplateStatus,
)
from app.modules.companies.schemas import (
    TemplateDetailResponse,
    TemplateLanguage,
    TemplateResponse,
)
from app.modules.companies.service import (
    get_company,
    get_template,
    get_template_html_cached,
    list_templates,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/staff/companies",
    tags=["staff-company-templates"],
)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "/{company_id}/templates",
    response_model=list[TemplateResponse],
)
async def list_templates_staff_endpoint(
    company_id: UUID,
    kind: DocumentTemplateKind | None = Query(default=None),
    language: TemplateLanguage | None = Query(default=None),
    status: TemplateStatus | None = Query(default=None),
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_reader),
) -> list[TemplateResponse]:
    """Staff list of templates for a company.

    Returns per-company rows + platform-default `active` fallbacks for
    any (kind, language) pair not covered by a per-company active row.
    The is_platform_default flag on each item is a Pydantic computed
    field derived from company_id (NULL -> True), so staff can tell
    overrides from fallbacks at a glance.

    Filtering:
      - `kind` / `language` apply to both branches.
      - `status` filters the per-company branch. The platform-default
        branch only ever holds active rows -- when status is set to
        anything other than `active`, fallbacks are excluded entirely
        (R2 §4.5, see service.list_templates docstring for the merge
        rules).
    """
    # Validate company exists. Returns NotFoundError -> 404 if missing.
    await get_company(company_id, session)

    # service.list_templates accepts plain strings for the filters; the
    # StrEnums coerce automatically because they ARE strings.
    rows = await list_templates(
        session=session,
        company_id=company_id,
        kind=kind,
        language=language,
        status=status,
    )

    return [TemplateResponse.model_validate(row) for row in rows]


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get(
    "/{company_id}/templates/{template_id}",
    response_model=TemplateDetailResponse,
)
async def get_template_staff_endpoint(
    company_id: UUID,
    template_id: UUID,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_reader),
) -> TemplateDetailResponse:
    """Staff detail of one template, including the inlined HTML body.

    Scope: returns rows owned by company_id OR platform-default rows
    (company_id IS NULL). 404 otherwise (cross-company id leakage is
    blocked the same way as in attachments).

    The HTML body is fetched via the cached helper so the staff inspect
    path shares cache warmth with the renderer (R2 §4.10). Asset files
    are NOT inlined here -- the response lists their filenames in
    `asset_files`; staff can drill into the MinIO Web UI from
    `storage_prefix` if they need to see the actual binaries.
    """
    # Validate company exists first so a 404 on company_id stays
    # distinguishable from a 404 on template_id.
    await get_company(company_id, session)

    template = await get_template(
        session=session,
        company_id=company_id,
        template_id=template_id,
    )

    html = await get_template_html_cached(template.storage_prefix)

    # Construct explicitly: TemplateDetailResponse adds html_content (not
    # an ORM column) and storage_prefix (an ORM column we surface only
    # on the detail surface). Building from kwargs is clearer than
    # juggling model_validate + model_copy across the missing field.
    return TemplateDetailResponse(
        id=template.id,
        company_id=template.company_id,
        kind=template.kind,
        language=template.language,
        version=template.version,
        title=template.title,
        status=template.status,
        asset_files=template.asset_files,
        created_by=template.created_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
        storage_prefix=template.storage_prefix,
        html_content=html,
    )
