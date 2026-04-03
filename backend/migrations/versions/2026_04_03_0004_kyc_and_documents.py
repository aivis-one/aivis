"""kyc and documents -- Phase 2 tables

Revision ID: 0004_kyc_and_documents
Revises: 0003_ledger_amount_bigint
Create Date: 2026-04-03 00:00:00.000000

Tables:
  - kyc_applications: KYC submission history (Sprint 2.1)
  - documents: versioned document templates (Sprint 2.2)
  - document_signings: immutable signing records (Sprint 2.2)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_kyc_and_documents"
down_revision: Union[str, None] = "0003_ledger_amount_bigint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create kyc_applications, documents, and document_signings tables."""

    # -------------------------------------------------------------------------
    # kyc_applications
    # -------------------------------------------------------------------------
    op.create_table(
        "kyc_applications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="submitted",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("""
        ALTER TABLE kyc_applications
            ADD CONSTRAINT ck_kyc_applications_status
                CHECK (status IN ('not_started', 'submitted', 'approved', 'rejected'))
    """)
    op.create_index(
        "ix_kyc_applications_user_id",
        "kyc_applications",
        ["user_id"],
    )
    op.create_index(
        "ix_kyc_applications_status",
        "kyc_applications",
        ["status"],
    )

    # -------------------------------------------------------------------------
    # documents
    # -------------------------------------------------------------------------
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column(
            "version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content_url", sa.String(2000), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("type", "version", name="uq_documents_type_version"),
    )
    op.execute("""
        ALTER TABLE documents
            ADD CONSTRAINT ck_documents_type
                CHECK (type IN (
                    'privacy_policy', 'terms_of_service',
                    'investment_agreement', 'agent_agreement',
                    'company_agreement'
                ))
    """)
    op.execute("""
        ALTER TABLE documents
            ADD CONSTRAINT ck_documents_status
                CHECK (status IN ('draft', 'active', 'archived'))
    """)
    op.create_index("ix_documents_type", "documents", ["type"])
    op.create_index("ix_documents_status", "documents", ["status"])

    # -------------------------------------------------------------------------
    # document_signings
    # -------------------------------------------------------------------------
    op.create_table(
        "document_signings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column(
            "signed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "document_id",
            name="uq_document_signings_user_document",
        ),
    )
    op.create_index(
        "ix_document_signings_user_id",
        "document_signings",
        ["user_id"],
    )
    op.create_index(
        "ix_document_signings_document_id",
        "document_signings",
        ["document_id"],
    )


def downgrade() -> None:
    """Drop Phase 2 tables in reverse dependency order."""
    op.drop_table("document_signings")
    op.drop_table("documents")
    op.drop_table("kyc_applications")
