# =============================================================================
# CBSHOME Backend -- Document Models (Sprint 2.2)
# =============================================================================
#
# Document:
#   Versioned document template managed by Staff. Status lifecycle:
#   draft -> active -> archived (see CBSHOME-State-Machines.md section 5).
#
# DocumentSigning:
#   Immutable record of user consent (checkbox). One per (user, document)
#   pair. No updated_at -- signings are never modified.
#
# DocumentType:
#   Concrete document categories. Role-to-type mapping lives in
#   documents/constants.py (ROLE_REQUIRED_DOCUMENT_TYPES).
#
# FUTURE (Phase 2+):
#   DocumentSigning gains docusign_envelope_id, docusign_signed_at via
#   ALTER ADD COLUMN. Module structure does not change.
# =============================================================================

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin, UUIDMixin


class DocumentType(enum.StrEnum):
    """Concrete document categories."""

    PRIVACY_POLICY = "privacy_policy"
    TERMS_OF_SERVICE = "terms_of_service"
    INVESTMENT_AGREEMENT = "investment_agreement"
    AGENT_AGREEMENT = "agent_agreement"
    COMPANY_AGREEMENT = "company_agreement"


class DocumentStatus(enum.StrEnum):
    """Document lifecycle status (State Machines v1.4 section 5)."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Document(UUIDMixin, TimestampMixin, Base):
    """Versioned document template managed by Staff."""

    __tablename__ = "documents"

    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    content_url: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=DocumentStatus.DRAFT,
        server_default=DocumentStatus.DRAFT.value,
        nullable=False,
        index=True,
    )

    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("type", "version", name="uq_documents_type_version"),
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} type={self.type} "
            f"v={self.version} status={self.status}>"
        )


class DocumentSigning(UUIDMixin, Base):
    """Immutable record of user consent (checkbox signing).

    No updated_at -- signings are never modified or deleted.
    """

    __tablename__ = "document_signings"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    ip_address: Mapped[str] = mapped_column(
        String(45),
        nullable=False,
    )

    user_agent: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "document_id",
            name="uq_document_signings_user_document",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentSigning id={self.id} user={self.user_id} "
            f"doc={self.document_id}>"
        )
