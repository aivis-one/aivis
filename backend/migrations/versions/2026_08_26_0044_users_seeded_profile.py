"""T-72: users.seeded_profile -- the marker `seed --reset` deletes by.

Adds one nullable column. NULL means "this person arrived through the
product"; a value means "scripts/seed.py created this row for the named
profile".

WHY THE COLUMN EXISTS AT ALL. `seed --reset` must decide, per row,
whether it is allowed to delete it. The reference implementation (velo)
answers that with a reserved telegram_id range, which does not transfer:
this product keys users by uuid and has no range to reserve. The other
candidate -- "delete everything at the demo e-mail domain" -- is not a
border either, because nothing prevents a real person from registering
at that domain, and --reset would then delete a customer. A column that
only the seed script ever writes is the narrowest thing that answers the
question correctly.

NO BACKFILL, DELIBERATELY. Rows created by the seed scripts this
delivery removes (seed_test_accounts.py, seed_storefront.py) stay NULL,
which reads as "not mine" -- so the new --reset will not touch them.
That is the safe direction and the intended one: those rows were made by
a mechanism that no longer exists, nobody can tell today which of them a
human has since logged into and used, and the loud way to clear a stand
of them is `db restore` or a reinstall, not a delete this migration
guesses at.

DOWNGRADE drops the column, and with it the only record of which rows
were synthetic. A stand downgraded and upgraded again has seeded rows
that --reset can no longer see; they become ordinary users. Stated
rather than fixed: reconstructing the marker would mean guessing, and
guessing is what the column exists to stop.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_users_seeded_profile"
down_revision: str | None = "0043_project_manage_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("seeded_profile", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_users_seeded_profile",
        "users",
        ["seeded_profile"],
    )


def downgrade() -> None:
    op.drop_index("ix_users_seeded_profile", table_name="users")
    op.drop_column("users", "seeded_profile")
