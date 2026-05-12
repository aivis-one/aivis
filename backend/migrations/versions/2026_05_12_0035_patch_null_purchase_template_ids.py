"""patch NULL purchase_agreement_template_id -- iter 2.5 bug fix

Revision ID: 0035_patch_null_purchase_tpl
Revises: 0034_attachments_lang_notnull
Create Date: 2026-05-12 00:00:00.000000

Root cause (iter 2.5):
  test_seed_platform_templates.py and test_reconcile_platform_templates.py
  have autouse fixtures that DELETE all company_document_templates rows
  with company_id IS NULL (platform defaults). The FK
  `fk_purchases_agreement_template_id` has ON DELETE SET NULL, so every
  Purchase that snapshotted a platform-default template (including archived
  versions replaced by a later reconcile) ended up with
  purchase_agreement_template_id = NULL after any pytest run containing
  those test files. The fixture teardown re-seeded with new rows but did
  not restore the NULLed purchase refs.

  The fixture code has been fixed in the same PR. This migration backfills
  purchases that were NULLed by previous test runs in the dev environment.

Fix:
  For every Purchase with purchase_agreement_template_id IS NULL, set it
  to the active platform-default `purchase_agreement / en` template. The
  4-stage fallback (R2 §4.7) guarantees this row exists after
  seed_platform_templates runs; cbshome update runs migrations AFTER
  seed_platform_templates, so the row is present here.

  We use `en` as the target language because:
    - All dev-environment purchases were snapshotted using the
      platform-en fallback (no per-company templates seeded).
    - The per-investor language is not stored on Purchase, so we can't
      reconstruct which language each purchase originally resolved.
    - `en` is the guaranteed last-resort fallback (R2 §4.7 stage 4) and
      the correct conservative choice for historical records.

Down-migration:
  No-op. Restoring NULLs would break agreement rendering for historical
  purchases, which is worse than pointing at the wrong template version.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0035_patch_null_purchase_tpl"
down_revision: Union[str, None] = "0034_attachments_lang_notnull"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Point NULL purchase_agreement_template_id at the active platform-en row."""
    op.execute(
        sa.text(
            """
            UPDATE purchases AS p
            SET    purchase_agreement_template_id = t.id
            FROM   company_document_templates AS t
            WHERE  p.purchase_agreement_template_id IS NULL
              AND  t.company_id   IS NULL
              AND  t.kind         = 'purchase_agreement'
              AND  t.language     = 'en'
              AND  t.status       = 'active'
            """
        )
    )


def downgrade() -> None:
    pass
