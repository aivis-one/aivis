"""kyc_approve stops being a hiring perk -- strip it from every
non-admin staff profile

Revision ID: 0051_kyc_approve_explicit
Revises: 0050_kyc_documents_and_settings
Create Date: 2026-09-05

NO SCHEMA CHANGE. This migration writes DATA into the existing
staff_profiles.permissions JSONB column. Mirror image of
0043_project_manage_backfill, and it is worth reading that file first:
this one uses the same predicate machinery to move a value in the
opposite direction, and for the opposite reason.

WHY THIS EXISTS. The companion code change flips kyc_approve's default
in DEFAULT_STAFF_PERMISSIONS from True to False, because H12 gives that
permission something real to hold: the identity documents behind every
verification. The flip alone would change nothing for anybody already
hired. create_staff() (staff/service.py) stores a FULL SNAPSHOT of
DEFAULT_STAFF_PERMISSIONS at creation time rather than a sparse
overrides dict, and seed.py writes every key True -- so every existing
profile carries an explicit {"kyc_approve": true}, and
_has_permission() reads the stored value before it ever consults the
default. The owner's ruling is that the permission is granted
explicitly, and a flip that leaves every current employee holding it
does not deliver that ruling for a single live account.

WHOSE KEY IS REMOVED, AND WHOSE IS NOT. Admins keep it. is_admin() is
"every key in VALID_PERMISSION_KEYS resolves True", so removing
kyc_approve from an admin's dict does not narrow that admin -- it
destroys their admin status outright, taking company_manage,
financial_operations and every other admin-gated action with it. That
is the exact hazard 0043 was written to prevent, arriving from the
other side. The predicate below therefore skips any profile that is an
admin under the CURRENT key set.

Removing the key rather than writing false: with the key absent,
_has_permission() falls through to the default, which is now False.
Should the owner ever decide the default was wrong, one edit in
constants.py restores the old behaviour for everyone who was never
explicitly granted or denied -- whereas an explicit false would have to
be found and deleted row by row. An absence says "never decided"; a
false says "decided against", and for these profiles nobody decided
anything, the value was inherited.

TIMING IS WHY THIS IS SAFE. The box was reinstalled and holds no live
non-admin staff, so this is close to a no-op today. Run six months from
now it would revoke the permission from people an admin had granted it
to on purpose, and there is no way for SQL to tell an inherited True
from a deliberate one -- both are just {"kyc_approve": true} in the
column. That distinction exists only in the present tense, which is
what makes now the only cheap moment to do this.

DOWNGRADE writes kyc_approve: true back into every profile that lacks
the key, which restores the pre-migration effective permission for
every row this migration touched. The honest caveat, same shape as
0043's: run late, it also grants the permission to profiles created
after this migration that never had it and were never meant to. A
rollback is meant to accompany the code revert that puts the default
back to True; run at that moment, the two agree.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051_kyc_approve_explicit"
down_revision: str | None = "0050_kyc_documents_and_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The ten keys of VALID_PERMISSION_KEYS with their defaults as they
# stand AFTER the companion code change, kyc_approve included at its
# new False. Spelled out as literals rather than imported: a migration
# that imports application constants starts lying the day somebody adds
# a permission.
#
# COALESCE(stored, default) per key, exactly as
# get_effective_permissions() resolves it -- a profile can be an admin
# by carrying explicit trues, or by never having overridden a key whose
# default is True, and both must read the same here as they do in
# Python.
_IS_ADMIN_PREDICATE = """
    COALESCE((permissions->>'avatar_mode')::boolean, TRUE) = TRUE
AND COALESCE((permissions->>'kyc_approve')::boolean, FALSE) = TRUE
AND COALESCE((permissions->>'payment_review')::boolean, TRUE) = TRUE
AND COALESCE((permissions->>'user_block')::boolean, TRUE) = TRUE
AND COALESCE((permissions->>'financial_operations')::boolean, TRUE) = TRUE
AND COALESCE((permissions->>'agent_application_review')::boolean, TRUE) = TRUE
AND COALESCE((permissions->>'translation_edit')::boolean, FALSE) = TRUE
AND COALESCE((permissions->>'company_manage')::boolean, TRUE) = TRUE
AND COALESCE((permissions->>'content_manage')::boolean, TRUE) = TRUE
AND COALESCE((permissions->>'project_manage')::boolean, FALSE) = TRUE
"""


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        # No :params -- every value is a literal permission key, not
        # user input, so there is nothing to bind.
        sa.text(
            f"""
            UPDATE staff_profiles
            SET permissions = permissions - 'kyc_approve'
            WHERE permissions ? 'kyc_approve'
              AND NOT ({_IS_ADMIN_PREDICATE})
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE staff_profiles
            SET permissions = permissions || '{"kyc_approve": true}'::jsonb
            WHERE NOT (permissions ? 'kyc_approve')
            """
        )
    )
