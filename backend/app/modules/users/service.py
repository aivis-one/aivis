# =============================================================================
# CBSHOME Backend -- Users Service (Sprint 1.3)
# =============================================================================
#
# RESPONSIBILITIES:
#   update_user() -- partial profile update via PATCH /users/me
#
# PARTIAL UPDATE STRATEGY:
#   Uses Pydantic model_dump(exclude_unset=True) to distinguish between
#   "field not sent" (absent from dict) and "field set to null" (present
#   with None value). This allows:
#     - Omitted fields: untouched
#     - Explicit null: rejected for NOT NULL columns (language)
#     - Explicit value: applied
#
# JSONB MUTATION:
#   profile is updated via set_jsonb() (JSONBMixin) which calls
#   flag_modified() internally. Direct assignment would silently
#   skip the DB write.
#
# REFRESH AFTER FLUSH:
#   After set_jsonb + flush, SQLAlchemy marks updated_at as expired.
#   session.refresh() reloads it to prevent MissingGreenlet when
#   Pydantic model_validate reads the attribute synchronously.
# =============================================================================

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.modules.users.models import User
from app.modules.users.schemas import UserUpdate

logger = structlog.get_logger()


async def update_user(
    user: User,
    body: UserUpdate,
    session: AsyncSession,
) -> User:
    """Partial update of user profile.

    Only fields present in the request body are updated.
    Does NOT commit -- caller manages transaction (P-01).

    Args:
        user: User object bound to the write session (TD-029).
        body: Pydantic model with optional fields.
        session: Write session (same as user is bound to).

    Returns:
        Updated User object with refreshed attributes.

    Raises:
        BadRequestError: If language is explicitly set to null.
    """
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        # Empty body -- nothing to update.
        return user

    # language: NOT NULL column -- reject explicit null.
    # Schema allows None as default ("not sent"), but explicit null
    # in JSON means the client wants to clear it -- not allowed.
    if "language" in updates and updates["language"] is None:
        raise BadRequestError("language cannot be set to null")

    # Apply language if provided.
    if "language" in updates:
        user.language = updates["language"]

    # Apply profile if provided (merge with existing JSONB).
    if "profile" in updates and updates["profile"] is not None:
        merged = dict(user.profile)
        merged.update(updates["profile"])
        user.set_jsonb("profile", merged)

    await session.flush()
    # Reload expired attrs (updated_at) after potential set_jsonb + flush.
    await session.refresh(user)

    logger.info(
        "user_profile_updated",
        user_id=str(user.id),
        fields=list(updates.keys()),
    )

    return user
