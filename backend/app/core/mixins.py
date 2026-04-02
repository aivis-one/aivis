# =============================================================================
# CBSHOME Backend -- ORM Mixins
# =============================================================================
#
# Reusable column sets for SQLAlchemy models.
#
# WHY MIXINS (not a custom Base)?
#   Alembic reads Base.metadata for autogenerate. Subclassing Base
#   would make mixin tables appear in metadata. Mixins with
#   __abstract__ = True avoid this entirely.
#
# USAGE:
#   class User(UUIDMixin, TimestampMixin, Base):
#       __tablename__ = "users"
#
# IMMUTABLE MODELS (AuditLog, ActiveLedger, PassiveLedger):
#   Use UUIDMixin only -- no TimestampMixin (no updated_at).
#   created_at is defined directly on the model as server_default.
# =============================================================================

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UUID as SA_UUID
from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.attributes import flag_modified


class UUIDMixin:
    """Primary key mixin -- UUID v4, app-side generated.

    App-side uuid4() ensures the ID is available immediately after
    object creation, before flush/commit. No round-trip needed.
    """

    id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class TimestampMixin:
    """Timestamp mixin -- created_at and updated_at.

    created_at: set once by the DB on INSERT (server_default).
    updated_at: set by SQLAlchemy ORM on every UPDATE (onupdate).

    NOTE: raw SQL bypasses onupdate. Always use ORM for mutations.

    Do NOT use this mixin on immutable models (AuditLog, ActiveLedger,
    PassiveLedger). Those define created_at directly without updated_at.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
    )


class JSONBMixin:
    """Safe JSONB mutation for SQLAlchemy models.

    PROBLEM:
        SQLAlchemy tracks column changes by comparing old vs new Python
        object identity. Mutating a dict in-place (obj.data["k"] = "v")
        or reassigning a shallow copy does NOT mark the column as dirty --
        the UPDATE is silently skipped. Data loss with no error.

    SOLUTION:
        Always use set_jsonb() to update JSONB columns. It assigns the
        new value AND calls flag_modified() to force SQLAlchemy to
        include the column in the next UPDATE statement.

    RULE:
        NEVER:  obj.data = new_dict
        NEVER:  obj.data["key"] = value
        ALWAYS: obj.set_jsonb("data", new_dict)

    All models with JSONB columns must inherit JSONBMixin.
    """

    def set_jsonb(self, field: str, value: dict) -> None:  # type: ignore[type-arg]
        """Safely assign a JSONB column value with change tracking.

        Args:
            field: Name of the JSONB column (e.g. "credentials", "plan_config").
            value: New dict to assign.

        Raises:
            AttributeError: If the field does not exist on the model.
        """
        setattr(self, field, value)
        flag_modified(self, field)
