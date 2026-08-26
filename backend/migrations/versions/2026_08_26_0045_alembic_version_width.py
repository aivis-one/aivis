"""Widen alembic_version.version_num so a revision id cannot be too long.

WHAT BROKE. alembic creates its own bookkeeping table with
version_num VARCHAR(32) unless the environment says otherwise, and
migrations/env.py said nothing. Revision ids in this tree are
descriptive and grew towards that ceiling for months without anyone
noticing: 0042_support_membership_backfill is exactly 32 characters --
the last one that fits -- and the next one, at 34, could not record
itself. The failure is not a nice one to read, either: the migration's
own body runs, THEN the version UPDATE raises
StringDataRightTruncationError, and the step rolls back. What the
operator sees is a database driver complaining about a string, with
nothing in the message connecting it to the name of the file.

WHY A MIGRATION AND NOT JUST A SETTING. version_table_column_length in
env.py (added alongside this) only applies when alembic CREATES the
table, so it fixes fresh databases and does nothing at all for every
box that already has one. Those need the ALTER, and an ALTER belongs in
a migration.

ORDERING. This runs after 0044 rather than before 0043, because
0043_project_manage_backfill was shortened to fit under the old ceiling
instead. So the rule for anyone adding a migration is positional:
     at or before this revision -> the id must fit in 32 characters
     after this revision        -> the id may use up to 64
tests/test_regression_guards.py enforces exactly that split by walking
the down_revision chain, so the rule is checked rather than remembered.

DOWNGRADE narrows the column back to 32. It is safe from here and only
from here: at the moment downgrade() runs, the stored value is this
revision's own id (26 characters), and everything below it fits by the
rule above. Downgrading from some future migration with a 40-character
id would have already stepped back through this one first.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_alembic_version_width"
down_revision: str | None = "0044_users_seeded_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept in one place so the guard test can read it instead of hard-coding
# a number that would silently drift away from this file.
VERSION_NUM_WIDTH = 64
LEGACY_VERSION_NUM_WIDTH = 32


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=LEGACY_VERSION_NUM_WIDTH),
        type_=sa.String(length=VERSION_NUM_WIDTH),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=VERSION_NUM_WIDTH),
        type_=sa.String(length=LEGACY_VERSION_NUM_WIDTH),
        existing_nullable=False,
    )
