"""kyc documents, the mode a session was decided under, and the first
staff-editable platform setting

Revision ID: 0050_kyc_documents_and_settings
Revises: 0049_kyc_gate_vocabulary
Create Date: 2026-09-05

THREE CHANGES, ONE REVISION, because they are one change of meaning: a
verification session stops being an empty row and starts carrying the
documents a human decides on, and the platform gains the switch that
says who that human is. Split apart, a partial upgrade leaves a tree
where POST /kyc/submit writes to a table that is not there.

  kyc_documents            NEW    the images themselves
  kyc_applications         + decision_mode, + document_type
  kyc_settings             NEW    exactly one row: who decides

WHY decision_mode IS NOT NULLABLE AND HAS A SERVER DEFAULT. Every row
that exists before this migration was decided by a staff member -- that
was the only path there was -- so 'manual' is not a guess, it is what
happened. A nullable column would have made those rows say "unknown"
about something we know, and every reader would need a branch for it.

WHY document_type IS NULLABLE AND HAS NO DEFAULT. The opposite case:
rows created by the person-level approval path never had a document,
and any default would make them claim a passport was shown. NULL here
means "no documents were ever submitted for this row", which is a fact,
not a gap.

kyc_settings IS ONE TYPED COLUMN, NOT A KEY/VALUE PAIR, and the first
draft of this migration had it the other way round. A generic
platform_settings table paid the whole price of an EAV shape -- an
untyped value, its meaning living in the reader, a CHECK constraint
growing one clause per key -- and bought none of the benefit, because
adding a setting still needed a migration for that clause. A
generalisation for a class with one member. The second setting adds a
column to whichever module owns it.

ONE ROW BY A CONSTANT PRIMARY KEY. A table with no key column has to
answer "which row" somehow; a constant id makes a second row impossible
at the database instead of by convention, and a concurrent first write
loses on the key rather than creating a twin.

NO FOREIGN KEY FROM kyc_documents TO A USER, deliberately: the document
belongs to the application, and the application already names the user.
A second path to the same fact is a second thing to keep level.

ondelete='RESTRICT' ON THE APPLICATION, matching kyc_applications ->
users. Storage is forever by ruling; a cascade would make deleting an
application silently destroy the evidence behind a decision, and the
objects in MinIO would survive it as unreferenced garbage nobody can
map back.

DOWNGRADE DROPS THE TABLES AND THE COLUMNS, and it does NOT touch
MinIO. Objects under kyc/applications/ outlive the rows that named
them; a downgrade that deleted them would make a rollback destroy the
only copy of somebody's identity documents. The operator who rolls back
across this revision inherits a prefix of unreferenced objects and is
told so here rather than surprised by it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0050_kyc_documents_and_settings"
down_revision: str | None = "0049_kyc_gate_vocabulary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Kept as literals rather than imported from app.modules.kyc.constants:
# a migration that imports application code breaks the day that code
# changes, and this file has to keep meaning the same thing forever.
# tests/test_kyc.py asserts these match the enums.
_DECISION_MODES = "'manual', 'automatic'"
_DOCUMENT_TYPES = "'passport', 'id_card', 'driving_licence'"
_DOCUMENT_KINDS = "'front', 'back', 'selfie'"


def upgrade() -> None:
    # -- kyc_applications: how it was decided, and what was shown ----------
    op.add_column(
        "kyc_applications",
        sa.Column(
            "decision_mode",
            sa.String(length=20),
            nullable=False,
            server_default="manual",
        ),
    )
    op.add_column(
        "kyc_applications",
        sa.Column("document_type", sa.String(length=30), nullable=True),
    )
    op.execute(
        f"""
        ALTER TABLE kyc_applications
        ADD CONSTRAINT ck_kyc_applications_decision_mode
        CHECK (decision_mode IN ({_DECISION_MODES}))
        """
    )
    op.execute(
        f"""
        ALTER TABLE kyc_applications
        ADD CONSTRAINT ck_kyc_applications_document_type
        CHECK (document_type IS NULL OR document_type IN ({_DOCUMENT_TYPES}))
        """
    )

    # -- kyc_documents ------------------------------------------------------
    op.create_table(
        "kyc_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kyc_applications.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_kyc_documents_application_id",
        "kyc_documents",
        ["application_id"],
    )
    # One front, one back, one selfie per application. Two rows of the
    # same kind would leave the panel showing whichever the query
    # ordered first, with nothing to say it was a choice.
    op.create_unique_constraint(
        "uq_kyc_documents_application_kind",
        "kyc_documents",
        ["application_id", "kind"],
    )
    # Two rows naming one object means one upload overwrote another
    # person's document. Keys are built from two UUID4s so this cannot
    # happen by accident -- which is exactly why a violation here is
    # worth hearing about rather than absorbing.
    op.create_unique_constraint(
        "uq_kyc_documents_storage_key",
        "kyc_documents",
        ["storage_key"],
    )
    op.execute(
        f"""
        ALTER TABLE kyc_documents
        ADD CONSTRAINT ck_kyc_documents_kind
        CHECK (kind IN ({_DOCUMENT_KINDS}))
        """
    )
    # An empty key would presign the bucket root; a non-positive size is
    # a row claiming a document that is not there.
    op.execute(
        """
        ALTER TABLE kyc_documents
        ADD CONSTRAINT ck_kyc_documents_storage_key_present
        CHECK (length(btrim(storage_key)) > 0)
        """
    )
    op.execute(
        """
        ALTER TABLE kyc_documents
        ADD CONSTRAINT ck_kyc_documents_size_positive
        CHECK (size_bytes > 0)
        """
    )

    # -- kyc_settings -------------------------------------------------------
    op.create_table(
        "kyc_settings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "verification_mode",
            sa.String(length=20),
            nullable=False,
            server_default="manual",
        ),
        sa.Column(
            "updated_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        f"""
        ALTER TABLE kyc_settings
        ADD CONSTRAINT ck_kyc_settings_verification_mode
        CHECK (verification_mode IN ({_DECISION_MODES}))
        """
    )

    # NO SEED ROW. An absent row is the documented "nobody has touched
    # this yet" state and the reader supplies the default; a seeded row
    # would claim somebody set it to manual, and its updated_by_id
    # would have to name a staff member who does not exist.


def downgrade() -> None:
    op.execute(
        "ALTER TABLE kyc_settings DROP CONSTRAINT ck_kyc_settings_verification_mode"
    )
    op.drop_table("kyc_settings")

    op.execute(
        "ALTER TABLE kyc_documents DROP CONSTRAINT ck_kyc_documents_size_positive"
    )
    op.execute(
        "ALTER TABLE kyc_documents DROP CONSTRAINT ck_kyc_documents_storage_key_present"
    )
    op.execute("ALTER TABLE kyc_documents DROP CONSTRAINT ck_kyc_documents_kind")
    op.drop_constraint(
        "uq_kyc_documents_storage_key", "kyc_documents", type_="unique"
    )
    op.drop_constraint(
        "uq_kyc_documents_application_kind", "kyc_documents", type_="unique"
    )
    op.drop_index("ix_kyc_documents_application_id", table_name="kyc_documents")
    # The rows go; the objects in MinIO do not. See the module docstring.
    op.drop_table("kyc_documents")

    op.execute(
        "ALTER TABLE kyc_applications DROP CONSTRAINT ck_kyc_applications_document_type"
    )
    op.execute(
        "ALTER TABLE kyc_applications DROP CONSTRAINT ck_kyc_applications_decision_mode"
    )
    op.drop_column("kyc_applications", "document_type")
    op.drop_column("kyc_applications", "decision_mode")
