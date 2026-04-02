"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all Sprint 0.3 tables in a single transaction."""

    # -- Enums --
    user_role = postgresql.ENUM(
        "investor", "agent", "company", "staff", "platform",
        name="user_role",
    )
    onboarding_step = postgresql.ENUM(
        "registered", "email_verified", "profile_complete",
        "kyc_done", "role_selected",
        name="onboarding_step",
    )
    kyc_status = postgresql.ENUM(
        "not_started", "submitted", "approved", "rejected",
        name="kyc_status",
    )
    ledger_status = postgresql.ENUM(
        "frozen", "confirmed", "reversed",
        name="ledger_status",
    )
    avatar_session_status = postgresql.ENUM(
        "active", "ended",
        name="avatar_session_status",
    )

    user_role.create(op.get_bind(), checkfirst=True)
    onboarding_step.create(op.get_bind(), checkfirst=True)
    kyc_status.create(op.get_bind(), checkfirst=True)
    ledger_status.create(op.get_bind(), checkfirst=True)
    avatar_session_status.create(op.get_bind(), checkfirst=True)

    # -------------------------------------------------------------------------
    # users
    # -------------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("investor", "agent", "company", "staff", "platform", name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "onboarding_step",
            sa.Enum(
                "registered", "email_verified", "profile_complete",
                "kyc_done", "role_selected",
                name="onboarding_step",
                create_type=False,
            ),
            server_default="registered",
            nullable=False,
        ),
        sa.Column(
            "kyc_status",
            sa.Enum("not_started", "submitted", "approved", "rejected", name="kyc_status", create_type=False),
            server_default="not_started",
            nullable=False,
        ),
        sa.Column("credentials", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("profile", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("language", sa.String(10), server_default="en", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_role", "users", ["role"])

    # -------------------------------------------------------------------------
    # active_ledger
    # -------------------------------------------------------------------------
    op.create_table(
        "active_ledger",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("frozen", "confirmed", "reversed", name="ledger_status", create_type=False),
            nullable=False,
        ),
        sa.Column("frozen_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origin_payment_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_active_ledger_user_id", "active_ledger", ["user_id"])
    op.create_index("ix_active_ledger_status", "active_ledger", ["status"])
    op.create_index(
        "ix_active_ledger_user_status",
        "active_ledger",
        ["user_id", "status"],
    )

    # -------------------------------------------------------------------------
    # passive_ledger
    # -------------------------------------------------------------------------
    op.create_table(
        "passive_ledger",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("frozen", "confirmed", "reversed", name="ledger_status", create_type=False),
            nullable=False,
        ),
        sa.Column("frozen_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origin_payment_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_passive_ledger_user_id", "passive_ledger", ["user_id"])
    op.create_index("ix_passive_ledger_status", "passive_ledger", ["status"])
    op.create_index(
        "ix_passive_ledger_user_status",
        "passive_ledger",
        ["user_id", "status"],
    )

    # -------------------------------------------------------------------------
    # staff_profiles
    # -------------------------------------------------------------------------
    op.create_table(
        "staff_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("permissions", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_staff_profiles_user_id"),
    )
    op.create_index("ix_staff_profiles_user_id", "staff_profiles", ["user_id"])

    # -------------------------------------------------------------------------
    # avatar_sessions
    # -------------------------------------------------------------------------
    op.create_table(
        "avatar_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("staff_id", sa.UUID(), nullable=False),
        sa.Column("target_user_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "ended", name="avatar_session_status", create_type=False),
            server_default="active",
            nullable=False,
        ),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["staff_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_avatar_sessions_staff_id", "avatar_sessions", ["staff_id"])
    op.create_index("ix_avatar_sessions_target_user_id", "avatar_sessions", ["target_user_id"])

    # -------------------------------------------------------------------------
    # audit_log
    # -------------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("event", sa.String(100), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("performed_by", sa.UUID(), nullable=True),
        sa.Column("on_behalf_of", sa.UUID(), nullable=True),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_event", "audit_log", ["event"])
    op.create_index("ix_audit_log_event_created", "audit_log", ["event", "created_at"])
    op.create_index("ix_audit_log_target", "audit_log", ["target_type", "target_id"])
    op.create_index("ix_audit_log_actor", "audit_log", ["actor_id"])


def downgrade() -> None:
    """Drop all Sprint 0.3 tables and enums."""
    op.drop_table("audit_log")
    op.drop_table("avatar_sessions")
    op.drop_table("staff_profiles")
    op.drop_table("passive_ledger")
    op.drop_table("active_ledger")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS avatar_session_status")
    op.execute("DROP TYPE IF EXISTS ledger_status")
    op.execute("DROP TYPE IF EXISTS kyc_status")
    op.execute("DROP TYPE IF EXISTS onboarding_step")
    op.execute("DROP TYPE IF EXISTS user_role")
