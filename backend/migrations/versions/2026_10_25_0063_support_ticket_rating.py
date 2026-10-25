"""support ticket rating (H41)

Revision ID: 0063_support_ticket_rating
Revises: 0062_support_operator_mutes
Create Date: 2026-10-25

Who resolved a ticket last, and the person's one rating of it: the stars,
the comment as written, the person's interface language when they rated
(not the language of the text -- nothing detects that), when, and the
operator the rating is about. models.SupportTicket says what each column
means. Every column is nullable: existing tickets have no resolver on
record and no rating.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0063_support_ticket_rating"
down_revision: str | None = "0062_support_operator_mutes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("resolved_by_user_id", "rated_resolver_user_id"):
        op.add_column(
            "support_tickets",
            sa.Column(
                name,
                sa.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    op.add_column("support_tickets", sa.Column("rating", sa.Integer(), nullable=True))
    op.add_column(
        "support_tickets", sa.Column("rating_comment", sa.Text(), nullable=True)
    )
    op.add_column(
        "support_tickets", sa.Column("rating_locale", sa.String(10), nullable=True)
    )
    op.add_column(
        "support_tickets",
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_support_tickets_rating",
        "support_tickets",
        "rating IS NULL OR rating BETWEEN 1 AND 5",
    )
    op.create_check_constraint(
        "ck_support_tickets_rating_whole",
        "support_tickets",
        "(rating IS NULL) = (rated_at IS NULL) "
        "AND (rating IS NULL) = (rating_locale IS NULL)",
    )
    op.create_check_constraint(
        "ck_support_tickets_rating_comment",
        "support_tickets",
        "rating IS NOT NULL OR rating_comment IS NULL",
    )


def downgrade() -> None:
    for name in (
        "ck_support_tickets_rating_comment",
        "ck_support_tickets_rating_whole",
        "ck_support_tickets_rating",
    ):
        op.drop_constraint(name, "support_tickets", type_="check")
    for name in (
        "rated_at",
        "rating_locale",
        "rating_comment",
        "rating",
        "rated_resolver_user_id",
        "resolved_by_user_id",
    ):
        op.drop_column("support_tickets", name)
