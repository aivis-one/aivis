"""kyc gate vocabulary -- five CHECK constraints in one revision

Revision ID: 0049_kyc_gate_vocabulary
Revises: 0048_crypto_webhook_events
Create Date: 2026-09-04

H10 gives KYC a price, a manual decision path and a revocation, and takes
the KYC step out of onboarding. Five CHECK constraints spell out the
vocabularies those touch, and Postgres has no ALTER CONSTRAINT for CHECK:
every one of them is drop + re-add.

  transactions.type            + 'kyc:verification_fee'   (widened)
  transactions.reference_type  + 'kyc_application'        (widened)
  users.kyc_status             + 'revoked'                (widened)
  kyc_applications.status      + 'revoked'                (widened)
  users.onboarding_step        - 'kyc_done'               (NARROWED)

ONE REVISION AND NOT FIVE, because they describe one change of meaning.
Split across five files, a partial upgrade leaves a tree where the code
writes a value the database rejects, and the operator has no single
revision to point at when asking what H10 did to the schema.

THE NARROWING ONE NEEDS AN UPDATE BEFORE THE RE-ADD. ADD CONSTRAINT
revalidates the whole table: a single users row still sitting on
'kyc_done' aborts the migration. This installation has no users, but a
migration is not allowed to be correct only against an empty table --
the import of the old user base is a scheduled event, and it will run
this file. Rows on 'kyc_done' go to 'role_selected', not to
'onboarding_complete': 'kyc_done' meant "role chosen, documents not
signed yet", and 'role_selected' is exactly that step once the KYC stage
between them is gone. Sending them to 'onboarding_complete' would mark
unsigned documents as signed.

DOWNGRADE IS NOT SYMMETRIC, deliberately. Re-adding 'kyc_done' is a
widening and always succeeds, but narrowing the other four back fails
the moment one row uses a value being removed -- a paid verification
fee, or a revoked approval. That is the same stance migration 0036 took
for the transaction log: those rows are facts, and a downgrade across
this revision has to decide their fate by hand rather than have the
migration guess.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0049_kyc_gate_vocabulary"
down_revision: str | None = "0048_crypto_webhook_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# -- transactions.type ------------------------------------------------------
# Fifteen literals since 0036; the sixteenth is the verification fee.
_TXN_TYPES_OLD = """
    'deposit:received', 'deposit:confirmed', 'deposit:reversed',
    'purchase:completed', 'purchase:gift', 'purchase:reversed',
    'installment:tranche_paid', 'installment:completed',
    'installment:defaulted',
    'withdrawal:created', 'withdrawal:confirmed',
    'withdrawal:rejected', 'withdrawal:completed',
    'withdrawal:failed',
    'reversal:completed'
"""

_TXN_TYPES_NEW = """
    'deposit:received', 'deposit:confirmed', 'deposit:reversed',
    'purchase:completed', 'purchase:gift', 'purchase:reversed',
    'installment:tranche_paid', 'installment:completed',
    'installment:defaulted',
    'withdrawal:created', 'withdrawal:confirmed',
    'withdrawal:rejected', 'withdrawal:completed',
    'withdrawal:failed',
    'reversal:completed',
    'kyc:verification_fee'
"""

# -- transactions.reference_type -------------------------------------------
# NULL stays allowed exactly as 0012 wrote it. The fee row does not use
# NULL: the id of the application the money bought is the only thing that
# answers "paid and not passed" when a user disputes the charge.
_TXN_REF_TYPES_OLD = "'payment', 'purchase', 'withdrawal', 'installment_plan'"
_TXN_REF_TYPES_NEW = (
    "'payment', 'purchase', 'withdrawal', 'installment_plan', "
    "'kyc_application'"
)

# -- KYC statuses (users.kyc_status and kyc_applications.status) -----------
# Two columns, two constraints, one vocabulary: users.kyc_status is a
# denormalised cache of kyc_applications.status. 'revoked' is ours, not a
# provider's -- staff produce it from the first day this ships.
_KYC_STATUSES_OLD = "'not_started', 'submitted', 'approved', 'rejected'"
_KYC_STATUSES_NEW = (
    "'not_started', 'submitted', 'approved', 'rejected', 'revoked'"
)

# -- users.onboarding_step -------------------------------------------------
_ONBOARDING_STEPS_OLD = """
    'registered',
    'email_verified',
    'profile_complete',
    'kyc_done',
    'role_selected',
    'onboarding_complete'
"""

_ONBOARDING_STEPS_NEW = """
    'registered',
    'email_verified',
    'profile_complete',
    'role_selected',
    'onboarding_complete'
"""


def upgrade() -> None:
    """Widen four vocabularies, narrow onboarding_step by one step."""
    # -- transactions.type --
    op.execute("ALTER TABLE transactions DROP CONSTRAINT ck_transactions_type")
    op.execute(
        f"""
        ALTER TABLE transactions
        ADD CONSTRAINT ck_transactions_type
        CHECK (type IN ({_TXN_TYPES_NEW}))
        """
    )

    # -- transactions.reference_type --
    op.execute(
        "ALTER TABLE transactions DROP CONSTRAINT ck_transactions_reference_type"
    )
    op.execute(
        f"""
        ALTER TABLE transactions
        ADD CONSTRAINT ck_transactions_reference_type
        CHECK (reference_type IS NULL OR reference_type IN (
            {_TXN_REF_TYPES_NEW}
        ))
        """
    )

    # -- users.kyc_status --
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_kyc_status")
    op.execute(
        f"""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_kyc_status
        CHECK (kyc_status IN ({_KYC_STATUSES_NEW}))
        """
    )

    # -- kyc_applications.status --
    op.execute(
        "ALTER TABLE kyc_applications DROP CONSTRAINT ck_kyc_applications_status"
    )
    op.execute(
        f"""
        ALTER TABLE kyc_applications
        ADD CONSTRAINT ck_kyc_applications_status
        CHECK (status IN ({_KYC_STATUSES_NEW}))
        """
    )

    # -- users.onboarding_step: drop, move the rows, re-add without the step --
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_onboarding_step")
    op.execute(
        """
        UPDATE users
        SET onboarding_step = 'role_selected'
        WHERE onboarding_step = 'kyc_done'
        """
    )
    op.execute(
        f"""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_onboarding_step
        CHECK (onboarding_step IN ({_ONBOARDING_STEPS_NEW}))
        """
    )


def downgrade() -> None:
    """Restore the pre-H10 vocabularies (see DOWNGRADE in the header).

    Rows carrying 'kyc:verification_fee', 'kyc_application' or 'revoked'
    make the matching re-add fail. Deleting or rewriting them here is not
    on offer: they are records of money taken and of decisions made.
    """
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_onboarding_step")
    op.execute(
        f"""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_onboarding_step
        CHECK (onboarding_step IN ({_ONBOARDING_STEPS_OLD}))
        """
    )

    op.execute(
        "ALTER TABLE kyc_applications DROP CONSTRAINT ck_kyc_applications_status"
    )
    op.execute(
        f"""
        ALTER TABLE kyc_applications
        ADD CONSTRAINT ck_kyc_applications_status
        CHECK (status IN ({_KYC_STATUSES_OLD}))
        """
    )

    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_kyc_status")
    op.execute(
        f"""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_kyc_status
        CHECK (kyc_status IN ({_KYC_STATUSES_OLD}))
        """
    )

    op.execute(
        "ALTER TABLE transactions DROP CONSTRAINT ck_transactions_reference_type"
    )
    op.execute(
        f"""
        ALTER TABLE transactions
        ADD CONSTRAINT ck_transactions_reference_type
        CHECK (reference_type IS NULL OR reference_type IN (
            {_TXN_REF_TYPES_OLD}
        ))
        """
    )

    op.execute("ALTER TABLE transactions DROP CONSTRAINT ck_transactions_type")
    op.execute(
        f"""
        ALTER TABLE transactions
        ADD CONSTRAINT ck_transactions_type
        CHECK (type IN ({_TXN_TYPES_OLD}))
        """
    )
