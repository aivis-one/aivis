# =============================================================================
# AIVIS.ONE Backend -- Agent Application Router (Sprint 7.1)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/agent-applications    -- submit application (investor only)
#   GET  /api/v1/agent-applications/me -- list my applications
#
# AUTH:
#   POST: get_current_user_write (write session, investor role checked in service).
#   GET:  get_current_user (read session).
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.agent_applications.schemas import (
    AgentApplicationListResponse,
    AgentApplicationResponse,
)
from app.modules.agent_applications.service import (
    get_my_applications,
    submit_application,
)
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/agent-applications", tags=["agent-applications"])


@router.post(
    "",
    response_model=AgentApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_agent_application(
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> AgentApplicationResponse:
    """Submit an agent role application.

    Only investors can apply. One pending application per user.
    Cooldown enforced after rejection.
    """
    application = await submit_application(user, session)
    return AgentApplicationResponse.model_validate(application)


@router.get(
    "/me",
    response_model=AgentApplicationListResponse,
)
async def list_my_applications(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> AgentApplicationListResponse:
    """List all agent applications for the authenticated user."""
    items, total = await get_my_applications(
        user.id, session, page=page, per_page=per_page
    )
    return AgentApplicationListResponse(
        items=[AgentApplicationResponse.model_validate(a) for a in items],
        total=total,
    )
