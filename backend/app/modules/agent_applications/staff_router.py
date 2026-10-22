# =============================================================================
# AIVIS.ONE Backend -- Agent Application Staff Router (Sprint 7.1)
# =============================================================================
#
# ENDPOINTS:
#   GET  /api/v1/staff/agent-applications         -- pending queue (paged, with applicant)
#   POST /api/v1/staff/agent-applications/{id}/approve -- approve
#   POST /api/v1/staff/agent-applications/{id}/reject  -- reject
#
# PERMISSIONS:
#   All endpoints require agent_application_review permission.
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
from app.modules.agent_applications.schemas import (
    AgentApplicationQueueItem,
    AgentApplicationQueueResponse,
    AgentApplicationResponse,
    RejectRequest,
)
from app.modules.agent_applications.staff_service import (
    agent_application_approve,
    agent_application_queue,
    agent_application_reject,
)
from app.modules.auth.dependencies import require_staff_permission
from app.modules.purchases.document_utils import extract_investor_name
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/staff/agent-applications",
    tags=["staff-agent-applications"],
)


@router.get(
    "",
    response_model=AgentApplicationQueueResponse,
)
async def get_agent_application_queue(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    staff: User = Depends(require_staff_permission("agent_application_review")),
    session: AsyncSession = Depends(get_db_reader),
) -> AgentApplicationQueueResponse:
    """Paged queue of pending applications with the applicant's name,
    e-mail and KYC status. Requires agent_application_review."""
    rows, total = await agent_application_queue(
        session, page=page, per_page=per_page
    )
    items = [
        AgentApplicationQueueItem(
            **AgentApplicationResponse.model_validate(application).model_dump(),
            applicant_name=extract_investor_name(applicant),
            applicant_email=applicant.email,
            applicant_kyc_status=applicant.kyc_status,
        )
        for application, applicant in rows
    ]
    return AgentApplicationQueueResponse(
        items=items, total=total, page=page, per_page=per_page
    )


@router.post(
    "/{application_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def approve_agent_application(
    application_id: UUID,
    staff: User = Depends(require_staff_permission("agent_application_review")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Approve agent application. Changes user role to agent."""
    await agent_application_approve(application_id, staff, session)


@router.post(
    "/{application_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reject_agent_application(
    application_id: UUID,
    body: RejectRequest,
    staff: User = Depends(require_staff_permission("agent_application_review")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Reject agent application. Sets cooldown period."""
    await agent_application_reject(application_id, staff, body.reason, session)
