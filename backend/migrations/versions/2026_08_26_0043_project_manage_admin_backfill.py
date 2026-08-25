"""project_manage admin backfill -- protects legacy admins from the
default flip

Revision ID: 0043_project_manage_admin_backfill
Revises: 0042_support_membership_backfill
Create Date: 2026-08-26 00:00:00.000000

NO SCHEMA CHANGE. This migration writes DATA into the existing
staff_profiles.permissions JSONB column.

WHY THIS EXISTS. A prior change (constants.py) added a `project_manage`
permission key with a default of True, intending it to gate
company/pool/product/attachment write endpoints to admin-only staff.
That default was wrong -- True did not narrow anything, since every
other permission in DEFAULT_STAFF_PERMISSIONS except translation_edit
already defaulted True. The companion code change (same commit as this
migration) flips that default to False, which is the only way the new
permission actually restricts anything.

THE HAZARD THE FLIP CREATES. is_admin() = every key in
VALID_PERMISSION_KEYS resolves True, with a missing key treated as
False. VALID_PERMISSION_KEYS is derived from DEFAULT_STAFF_PERMISSIONS,
so it now includes project_manage. Every StaffProfile row created
BEFORE project_manage existed has a permissions dict with no
project_manage key at all -- there was nothing to put there at the
time. The moment the new False default ships, get_effective_permissions()
(defaults merged with stored overrides) resolves project_manage to
False for every one of those rows, and is_admin() flips from True to
False for every staff member who was a full admin under the OLD key
set. Real admins -- possibly the only staff account that exists right
now -- would silently lose admin-gated actions (e.g. hard-delete) the
instant this deploys, with no error and no signal beyond "it stopped
working". This migration is the fix: it writes project_manage: true
into the permissions of every profile that qualified as admin under
the pre-existing 9 keys, so is_admin() reads exactly the same before
and after the deploy for every profile that was already an admin.

THE PREDICATE. "Admin under the old key set" means: for each of
avatar_mode, kyc_approve, payment_review, user_block,
financial_operations, agent_application_review, translation_edit,
company_manage, content_manage -- the stored override if present,
else that key's CURRENT default (unaffected by this change; only
project_manage's default is moving) -- resolves True. translation_edit
defaults False, so an old-set admin must carry an explicit
{"translation_edit": true} override; the other eight all default True,
so a legacy admin profile can satisfy them by simply never having
overridden them (the common case) or by having them explicitly True.

WHY WE ONLY TOUCH ROWS WHERE project_manage IS ABSENT (an addition
beyond a literal reading of "admin -> set true"). Every profile
created via the real create_staff() service (or the test factory that
mirrors it) stores a full snapshot of DEFAULT_STAFF_PERMISSIONS at
creation time, not a sparse overrides dict. Any profile created AFTER
project_manage was added to that dict already carries an explicit
project_manage key -- True from the (soon to be corrected) old
default, or some other value if an admin already used
PATCH /staff/users/{id}/permissions to set it deliberately. Blindly
merging project_manage: true into every row that passes the 9-key
predicate would silently overwrite a deliberate PATCH revocation
(project_manage: false) for any admin-on-the-other-9-keys profile. A
backfill should fill an absence, not clobber an explicit prior
decision, so the WHERE clause requires the key to be missing entirely
-- which is true precisely for the legacy rows this migration exists
to protect, and never true for anything touched by application code
after project_manage existed.

NOT FILTERED BY is_active. A deactivated legacy admin who gets
reactivated later must still read back as admin; the operational flag
and the permission snapshot are independent, and 0042 next door
happens to filter by is_active for an unrelated reason (only active
staff are declared members of a live roster) that does not apply here.

Raw SQL rather than the ORM, one atomic UPDATE per direction, same
convention as 0042_support_membership_backfill: a migration that
imported StaffProfile would break the day that model changes, and this
one only needs one table and one JSONB column. The predicate is
expressed entirely in SQL (COALESCE over ->> text casts) rather than
fetched-and-looped in Python so the whole backfill commits as a single
statement -- there is no "half the rows updated" state to worry about,
unlike 0042 where the multi-row INSERT needed the surrounding
transaction to do that job instead.

DOWNGRADE. project_manage did not exist as a concept before this
migration -- no row could have carried the key. The literal inverse is
therefore to strip the key from every row that currently has it, not
just the rows this migration itself wrote (we do not keep a manifest
of which those were, and manufacturing one -- e.g. a temp marker
column -- would be schema churn for a rollback path that pairs with a
code revert removing project_manage from VALID_PERMISSION_KEYS
entirely). Downgrade is meant to accompany exactly that code revert,
at which point project_manage becomes an unrecognized key again and
its presence or absence is moot to is_admin() either way -- but
leaving stale keys around after a real rollback is worse hygiene than
clearing them, and matches the pre-migration data shape exactly. The
one honest caveat (same shape as 0042's downgrade note): if downgrade
runs long after upgrade, after staff have legitimately used PATCH to
set project_manage on new profiles, this also erases that activity.
That is the accepted cost of a rollback run late instead of promptly.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_project_manage_admin_backfill"
down_revision: str | None = "0042_support_membership_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        # No :params -- every value here is a literal permission key or
        # a literal default, not user input, so there is nothing to bind.
        sa.text(
            """
            UPDATE staff_profiles
            SET permissions = permissions || '{"project_manage": true}'::jsonb
            WHERE NOT (permissions ? 'project_manage')
              AND COALESCE((permissions->>'avatar_mode')::boolean, TRUE) = TRUE
              AND COALESCE((permissions->>'kyc_approve')::boolean, TRUE) = TRUE
              AND COALESCE((permissions->>'payment_review')::boolean, TRUE) = TRUE
              AND COALESCE((permissions->>'user_block')::boolean, TRUE) = TRUE
              AND COALESCE((permissions->>'financial_operations')::boolean, TRUE) = TRUE
              AND COALESCE((permissions->>'agent_application_review')::boolean, TRUE) = TRUE
              AND COALESCE((permissions->>'translation_edit')::boolean, FALSE) = TRUE
              AND COALESCE((permissions->>'company_manage')::boolean, TRUE) = TRUE
              AND COALESCE((permissions->>'content_manage')::boolean, TRUE) = TRUE
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE staff_profiles
            SET permissions = permissions - 'project_manage'
            WHERE permissions ? 'project_manage'
            """
        )
    )
