# =============================================================================
# CBSHOME Backend -- Users Service (Sprint 1.3, fix TD-024, Sprint 6.3, F2.3)
# =============================================================================
#
# RESPONSIBILITIES:
#   update_user()           -- partial profile update via PATCH /users/me
#   select_role()           -- onboarding role selection (F2.3)
#   update_payout_details() -- set withdrawal payment methods (Sprint 6.3)
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
#
# PROFILE KEY WHITELIST (TD-024):
#   Only allowed keys are accepted in profile JSONB. Prevents mass
#   assignment of arbitrary keys (e.g. "is_admin", "role", "__proto__").
#
# AUDIT:
#   Profile changes are recorded in audit_log for compliance.
#   Country and phone changes are especially significant for
#   financial platform AML/KYC requirements.
# =============================================================================

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError
from app.modules.users.models import OnboardingStep, User, UserRole
from app.modules.users.schemas import UserUpdate

logger = structlog.get_logger()

# Whitelist of allowed keys in profile JSONB (TD-024).
# Any key not in this set is rejected with 400.
_ALLOWED_PROFILE_KEYS = frozenset({
    "first_name",
    "last_name",
    "country",
    "phone",
    "avatar_url",
})

# Profile fields required to advance to profile_complete step.
_REQUIRED_PROFILE_FIELDS = frozenset({"first_name", "last_name", "country"})


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
        BadRequestError: If language is explicitly set to null,
            or if profile contains unknown keys.
    """
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        # Empty body -- nothing to update.
        return user

    # language: NOT NULL column -- reject explicit null.
    if "language" in updates and updates["language"] is None:
        raise BadRequestError("language cannot be set to null")

    # Apply language if provided.
    if "language" in updates:
        user.language = updates["language"]

    # Apply profile if provided (merge with existing JSONB).
    if "profile" in updates and updates["profile"] is not None:
        incoming = updates["profile"]

        # TD-024: reject unknown keys to prevent mass assignment.
        extra = set(incoming.keys()) - _ALLOWED_PROFILE_KEYS
        if extra:
            raise BadRequestError(
                f"Unknown profile keys: {sorted(extra)}"
            )

        merged = dict(user.profile)
        merged.update(incoming)
        user.set_jsonb("profile", merged)

    # Advance onboarding step if profile requirements are met.
    if user.onboarding_step == OnboardingStep.EMAIL_VERIFIED:
        profile = user.profile or {}
        if all(profile.get(f) for f in _REQUIRED_PROFILE_FIELDS):
            user.onboarding_step = OnboardingStep.PROFILE_COMPLETE

    await session.flush()
    # Reload expired attrs (updated_at) after potential set_jsonb + flush.
    await session.refresh(user)

    # Audit: profile changes are compliance-significant
    # (country, phone affect AML/KYC).
    await record_audit(
        session=session,
        event="user.profile_updated",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={"fields": list(updates.keys())},
    )

    logger.info(
        "user_profile_updated",
        user_id=str(user.id),
        fields=list(updates.keys()),
    )

    return user


# ---------------------------------------------------------------------------
# Role selection (F2.3 -- Onboarding)
# ---------------------------------------------------------------------------


async def select_role(
    user: User,
    role: str,
    session: AsyncSession,
) -> User:
    """Select a role during onboarding.

    Only allowed when onboarding_step == profile_complete.
    Changes user.role and advances to role_selected.

    Args:
        user: User object bound to write session.
        role: Target role (investor, agent, company). Already
              validated by SelectRoleRequest schema.
        session: Write session.

    Returns:
        Updated User with refreshed attributes.

    Raises:
        BadRequestError: If onboarding_step is not profile_complete.
    """
    if user.onboarding_step != OnboardingStep.PROFILE_COMPLETE:
        raise BadRequestError(
            f"Role selection requires onboarding_step=profile_complete "
            f"(current: {user.onboarding_step})"
        )

    old_role = user.role
    user.role = role
    user.onboarding_step = OnboardingStep.ROLE_SELECTED

    await session.flush()
    await session.refresh(user)

    await record_audit(
        session=session,
        event="user.role_selected",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={"old_role": old_role, "new_role": role},
    )

    logger.info(
        "user_role_selected",
        user_id=str(user.id),
        old_role=old_role,
        new_role=role,
    )

    return user


# ---------------------------------------------------------------------------
# Payout details (Sprint 6.3)
# ---------------------------------------------------------------------------


async def update_payout_details(
    user: User,
    payout_details: dict[str, Any],
    session: AsyncSession,
) -> User:
    """Replace user's payout details (withdrawal payment methods).

    Full replacement -- not merge. Previous value is overwritten.
    Does NOT commit -- caller manages transaction (P-01).

    Args:
        user: User object bound to write session.
        payout_details: New payout details dict.
        session: Write session.

    Returns:
        Updated User with refreshed attributes.
    """
    user.set_jsonb("payout_details", payout_details)
    await session.flush()
    await session.refresh(user)

    await record_audit(
        session=session,
        event="user.payout_details_updated",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={},
    )

    logger.info(
        "payout_details_updated",
        user_id=str(user.id),
    )

    return user
