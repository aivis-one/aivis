# =============================================================================
# AIVIS.ONE Backend -- Document Models (Sprint 2.2, updated by 0024, 0025)
# =============================================================================
#
# Document:
#   Versioned document template. Status lifecycle:
#   draft -> active -> archived (see AIVIS-State-Machines.md section 5).
#
#   Since migration 0024 the HTML body of a document lives as a static
#   file served by the frontend. The backend only stores metadata.
#   `type` is a free-form string (not an enum) so legal can add new
#   categories by dropping an HTML file with proper <meta> tags into
#   the legal folder; no code change needed.
#
#   Migration 0025 added per-language rows: the same `type` can exist
#   in multiple languages, and the user signs the exact copy they read.
#   Static path: frontend/public/legal/<language>/<type>.html.
#   Uniqueness is now (type, version, language).
#
#   `content_hash` is a sha256 hex digest of the HTML body. Seed reads
#   the file, computes the hash, and compares against the current active
#   row for the same (type, language). If hashes differ the current row
#   is archived and a new one is created with version+1. The hash column
#   is never exposed through the API -- it is an internal seed artefact.
#
# DocumentSigning:
#   Immutable record of user consent (checkbox). One per (user, document)
#   pair. No updated_at -- signings are never modified.
# =============================================================================

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import JSONBMixin, TimestampMixin, UUIDMixin


class DocumentStatus(enum.StrEnum):
    """Document lifecycle status (State Machines v1.4 section 5)."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Document(JSONBMixin, UUIDMixin, TimestampMixin, Base):
    """Versioned document template, one row per (type, version, language).

    The HTML body is NOT stored here -- it lives at
    frontend/public/legal/<language>/<type>.html and is served as static
    content by the frontend. Seed reads those files on install/update
    to populate this table with metadata (title, type, language,
    required_for_roles, content_hash).
    """

    __tablename__ = "documents"

    # Free-form string; acceptable values are driven by files in
    # frontend/public/legal/<language>/ (one HTML per type per language).
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

    # ISO 639-1 language code, e.g. "en", "ru", "de", "ar". Drives both
    # the static-file path and the language a user signs in.
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="en",
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # JSONB array of role names, e.g. ["investor", "agent"]. Signals
    # which user roles must sign this document during onboarding.
    # Mutations must go through set_jsonb("required_for_roles", value)
    # (see JSONBMixin) to be flagged as dirty by SQLAlchemy.
    required_for_roles: Mapped[list] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    # SHA-256 hex digest of the HTML body. Used by seed to detect edits:
    # if the current file's hash differs from the active row for the
    # same (type, language), seed archives the row and creates a new one
    # with incremented version. Not exposed via the API.
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="",
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
        UniqueConstraint(
            "type", "version", "language",
            name="uq_documents_type_version_language",
        ),
        Index(
            "ix_documents_type_language_status",
            "type", "language", "status",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} type={self.type} "
            f"v={self.version} lang={self.language} status={self.status}>"
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
