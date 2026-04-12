# =============================================================================
# CBSHOME Backend -- Notification Staff Router (Sprint 8.2)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/staff/notifications/templates/reload -- reload template cache
#
# PERMISSIONS:
#   Requires translation_edit permission.
#
# COMMIT RULE (P-01):
#   No DB writes -- stateless cache operation.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends, status

from app.modules.auth.dependencies import require_staff_permission
from app.modules.notifications.template_engine import reload_templates
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/staff/notifications",
    tags=["staff-notifications"],
)


@router.post(
    "/templates/reload",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reload_notification_templates(
    staff: User = Depends(require_staff_permission("translation_edit")),
) -> None:
    """Reload notification templates from disk.

    Clears the in-memory template cache. Next notification delivery
    will load fresh YAML files. Requires translation_edit permission.
    """
    reload_templates()
    logger.info(
        "templates_reloaded_by_staff",
        staff_id=str(staff.id),
    )
