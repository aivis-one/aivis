"""fk indexes -- TASK-6 4.4, index unindexed foreign-key columns

Revision ID: 0039_fk_indexes
Revises: 0038_tranche_reversed
Create Date: 2026-08-14 00:00:00.000000

Indexes every foreign-key column under backend/app/modules/**/models.py that
had no index covering it as its leading column (own index, unique
constraint, leading column of a composite index/constraint, or primary key
all already count as covered and are untouched here).

16 columns. The set was 19 when this file was written and the Navigator's
LEAN check removed three; the correction is recorded here rather than in a
silent edit, because the CAUSE matters more than the count.

posts.owner_id and posts.created_by were ALREADY INDEXED -- ix_posts_owner_id
and ix_posts_created_by are created by migration 0022_posts, and re-creating
them raises "relation already exists", which aborts the whole migration. On
the owner's box a failed migration leaves the site DOWN (runbook Part Two,
§9), so this was not a cosmetic defect.
post_dismissals.post_id is the leading column of uq_post_dismissals_post_user
(post_id, user_id) from the same migration -- already covered, and excluded
under exactly the rule already applied to volume_payouts.agent_id below.
post_dismissals.user_id is NOT the leading column of that constraint and
correctly stays.

ROOT CAUSE, one sentence: the set was derived by reading models.py, and an
index or constraint that lives only in a MIGRATION is invisible to that
method. The same blind spot was identified in the other direction below --
two real FK constraints that exist only in a migration -- and not applied
back. THE MODEL IS NOT THE SCHEMA; the migration history is.

Of the 16: 14 are declared via SQLAlchemy's ForeignKey() in their
model and would show up in a grep for that literal string. The other 2 --
active_ledger.origin_payment_id and passive_ledger.origin_payment_id -- are
plain UUID columns in ledgers/models.py with a REAL foreign-key constraint
that exists only at the DB level (added by migration 0007_payments via
op.create_foreign_key, never wrapped in ForeignKey() in the model, per that
model's own "Circular FK to payments.id" comment). A ForeignKey()-only sweep
of models.py would miss both.

volume_payouts.agent_id is NOT in this migration despite being a natural
candidate: it is the leading column of the composite unique constraint
uq_volume_payouts_agent_period (agent_id, period_type, period_start), which
already covers it -- adding a second index on the same leading column would
be redundant.

Plain CREATE INDEX, not CONCURRENTLY: CONCURRENTLY cannot run inside a
transaction, which is how Alembic runs this migration, and its only reason
to exist is avoiding a write lock on a live database. `aivis update`
(runbook Part Two, §9) takes the whole site offline for its entire run, so
there are no concurrent writes to block.

Downgrade drops every index this migration creates, in reverse order.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0039_fk_indexes"
down_revision: Union[str, None] = "0038_tranche_reversed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create indexes on 16 previously-unindexed foreign-key columns."""
    op.create_index(
        "ix_purchases_purchase_agreement_template_id",
        "purchases",
        ["purchase_agreement_template_id"],
    )
    op.create_index(
        "ix_payments_origin_payment_id",
        "payments",
        ["origin_payment_id"],
    )
    op.create_index(
        "ix_documents_created_by",
        "documents",
        ["created_by"],
    )
    op.create_index(
        "ix_post_dismissals_user_id",
        "post_dismissals",
        ["user_id"],
    )
    op.create_index(
        "ix_events_created_by",
        "events",
        ["created_by"],
    )
    op.create_index(
        "ix_installment_plans_product_installment_id",
        "installment_plans",
        ["product_installment_id"],
    )
    op.create_index(
        "ix_installment_plans_agent_id",
        "installment_plans",
        ["agent_id"],
    )
    op.create_index(
        "ix_installment_tranches_purchase_id",
        "installment_tranches",
        ["purchase_id"],
    )
    op.create_index(
        "ix_company_price_history_changed_by",
        "company_price_history",
        ["changed_by"],
    )
    op.create_index(
        "ix_company_roadmap_items_post_id",
        "company_roadmap_items",
        ["post_id"],
    )
    op.create_index(
        "ix_company_roadmap_items_linked_product_id",
        "company_roadmap_items",
        ["linked_product_id"],
    )
    op.create_index(
        "ix_company_attachments_created_by",
        "company_attachments",
        ["created_by"],
    )
    op.create_index(
        "ix_company_document_templates_created_by",
        "company_document_templates",
        ["created_by"],
    )
    op.create_index(
        "ix_agent_applications_reviewed_by",
        "agent_applications",
        ["reviewed_by"],
    )
    op.create_index(
        "ix_active_ledger_origin_payment_id",
        "active_ledger",
        ["origin_payment_id"],
    )
    op.create_index(
        "ix_passive_ledger_origin_payment_id",
        "passive_ledger",
        ["origin_payment_id"],
    )


def downgrade() -> None:
    """Drop all 16 indexes created by upgrade(), in reverse order."""
    op.drop_index("ix_passive_ledger_origin_payment_id", "passive_ledger")
    op.drop_index("ix_active_ledger_origin_payment_id", "active_ledger")
    op.drop_index("ix_agent_applications_reviewed_by", "agent_applications")
    op.drop_index(
        "ix_company_document_templates_created_by", "company_document_templates"
    )
    op.drop_index("ix_company_attachments_created_by", "company_attachments")
    op.drop_index(
        "ix_company_roadmap_items_linked_product_id", "company_roadmap_items"
    )
    op.drop_index("ix_company_roadmap_items_post_id", "company_roadmap_items")
    op.drop_index("ix_company_price_history_changed_by", "company_price_history")
    op.drop_index("ix_installment_tranches_purchase_id", "installment_tranches")
    op.drop_index("ix_installment_plans_agent_id", "installment_plans")
    op.drop_index(
        "ix_installment_plans_product_installment_id", "installment_plans"
    )
    op.drop_index("ix_events_created_by", "events")
    op.drop_index("ix_post_dismissals_user_id", "post_dismissals")
    op.drop_index("ix_documents_created_by", "documents")
    op.drop_index("ix_payments_origin_payment_id", "payments")
    op.drop_index(
        "ix_purchases_purchase_agreement_template_id", "purchases"
    )
