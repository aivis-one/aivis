# =============================================================================
# AIVIS.ONE Backend -- Staff Permission Helpers (extracted Phase 4 fix)
# =============================================================================
#
# Shared helpers for staff routers that need fine-grained permission checks
# beyond the base require_staff_permission() dependency.
#
# Previously duplicated in companies/staff_router.py and
# products/staff_router.py. Consolidated here as single source.
# =============================================================================

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.modules.staff.service import get_effective_permissions, get_staff_profile
from app.modules.users.models import User


async def require_permission(
    staff: User,
    permission: str,
    session: AsyncSession,
) -> None:
    """Check that staff has a specific permission.

    Raises:
        ForbiddenError: If permission is missing.
    """
    profile = await get_staff_profile(staff.id, session)
    if not profile:
        raise ForbiddenError("Staff profile not found")
    effective = get_effective_permissions(profile)
    if not effective.get(permission, False):
        raise ForbiddenError(f"Permission '{permission}' required")


async def require_financial_operations(
    staff: User,
    session: AsyncSession,
) -> None:
    """Check that staff has financial_operations permission."""
    await require_permission(staff, "financial_operations", session)
