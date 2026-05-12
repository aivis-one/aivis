# =============================================================================
# CBSHOME Backend -- Seed Platform Default Templates Tests
#                     (Refactor 2 iter 2.3, R2 §4.9)
# =============================================================================
#
# Coverage:
#   - First run on empty DB inserts 16 active rows (4 kinds x 4 langs).
#   - Second run is a no-op: skipped=16, created=0.
#
# ISOLATION:
#   Each test wipes platform-default rows + the test bucket's
#   `_platform/` prefix in setup, then in teardown re-uploads the
#   bootstrap files from `backend/scripts/templates/_default/` and
#   re-runs the seed so the shared dev DB and the next consumer see
#   the canonical 16-row state.
#
# Email prefix: "seedp_" (no test users registered, but kept for
# consistency with other test files).
# =============================================================================

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import (
    delete_object,
    list_objects,
    upload_object,
)
from app.modules.companies.constants import (
    DocumentTemplateKind,
    TemplateStatus,
)
from app.modules.companies.models import CompanyDocumentTemplate
from app.modules.purchases.models import Purchase
from scripts.seed_platform_templates import (
    seed_platform_templates,
)

EMAIL_PREFIX = "seedp_"
TEST_BUCKET = "cbshome-attachments-test"
KINDS = (
    "purchase_agreement",
    "gift_certificate",
    "installment_subcontract",
    "ownership_certificate",
)
LANGS = ("en", "ru", "de", "ar")
ASSET_FILES = ("logo.png", "signature.png", "stamp.png")
HTML_NAME = "template.html"

# Path to bootstrap files in the repo. In the app container the tests
# run from /app/tests/, scripts live at /app/scripts/, so .parent.parent
# resolves to /app and the join below lands at /app/scripts/templates/_default.
SEED_DIR = Path(__file__).resolve().parent.parent / "scripts" / "templates" / "_default"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def use_test_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[None, None]:
    """Point storage at the dedicated test bucket and drain it before each test."""
    monkeypatch.setattr(settings, "minio_bucket", TEST_BUCKET)
    keys = await list_objects("")
    for key in keys:
        await delete_object(key)
    yield


@pytest.fixture(autouse=True)
async def isolate_platform_templates(
    use_test_bucket,  # ensures bucket switch + drain runs first
    db_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """SETUP: wipe platform-default rows + MinIO `_platform/` (in test bucket).
    TEARDOWN: re-upload bootstrap files, re-run seed, and relink any
    Purchase rows whose snapshotted template was just wiped.

    Without the relink pass, the platform-template DELETE here cascades
    via FK ON DELETE SET NULL onto purchases.purchase_agreement_template_id
    and leaves Purchase rows orphaned even after the seed re-creates the
    canonical 16 rows (with FRESH UUIDs that won't match the old
    snapshots). Save (purchase_id, kind, language) before the DELETE,
    then in teardown match each saved triple to the freshly-seeded
    active template and UPDATE the Purchase row back to a valid id.
    """
    # SETUP -- snapshot which purchases will be orphaned by the DELETE
    # below. Only rows whose current snapshot lives on a platform-default
    # template (company_id IS NULL on the joined template row) are at
    # risk; company-scoped snapshots are unaffected.
    saved_refs = (
        await db_session.execute(
            select(
                Purchase.id,
                CompanyDocumentTemplate.kind,
                CompanyDocumentTemplate.language,
            )
            .join(
                CompanyDocumentTemplate,
                Purchase.purchase_agreement_template_id
                == CompanyDocumentTemplate.id,
            )
            .where(CompanyDocumentTemplate.company_id.is_(None))
        )
    ).all()

    # SETUP -- wipe DB rows.
    await db_session.execute(
        delete(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.company_id.is_(None)
        )
    )
    await db_session.commit()

    # SETUP -- wipe MinIO _platform/ in the active (test) bucket. The
    # use_test_bucket fixture already drained the whole bucket, so this
    # is mostly a defensive sweep in case future fixtures stop draining.
    platform_keys = await list_objects("_platform/")
    for key in platform_keys:
        await delete_object(key)

    yield

    # TEARDOWN -- re-upload bootstrap files into the active (test)
    # bucket under _platform/templates/<kind>/<lang>/, then call the
    # seed function to recreate the 16 rows. Tests in other files that
    # rely on platform defaults pick up the restored state on their
    # next run.
    for kind in KINDS:
        for lang in LANGS:
            src_dir = SEED_DIR / kind / lang
            dst_prefix = f"_platform/templates/{kind}/{lang}/"
            html_bytes = (src_dir / HTML_NAME).read_bytes()
            await upload_object(
                dst_prefix + HTML_NAME,
                html_bytes,
                "text/html; charset=utf-8",
            )
            for asset in ASSET_FILES:
                asset_bytes = (src_dir / asset).read_bytes()
                await upload_object(
                    dst_prefix + asset,
                    asset_bytes,
                    "image/png",
                )
    await seed_platform_templates(db_session, dry_run=False)
    await db_session.commit()

    # TEARDOWN -- relink purchases that lost their snapshot to the FK
    # SET NULL. Match each saved (kind, language) triple to the newly-
    # seeded active platform-default row and UPDATE the Purchase. If
    # a match is somehow missing, leave that Purchase NULL rather than
    # corrupting it -- regression test catches that via assert.
    for purchase_id, kind, lang in saved_refs:
        new_tpl_id = (
            await db_session.execute(
                select(CompanyDocumentTemplate.id).where(
                    CompanyDocumentTemplate.company_id.is_(None),
                    CompanyDocumentTemplate.kind == kind,
                    CompanyDocumentTemplate.language == lang,
                    CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
                )
            )
        ).scalar_one_or_none()
        if new_tpl_id is not None:
            await db_session.execute(
                update(Purchase)
                .where(Purchase.id == purchase_id)
                .values(purchase_agreement_template_id=new_tpl_id)
            )
    if saved_refs:
        await db_session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_creates_all_16_pairs_on_empty_db(
    db_session: AsyncSession,
) -> None:
    """Empty platform-defaults table -> seed creates 16 rows, all active."""
    # Sanity: setup wiped the rows.
    pre = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.company_id.is_(None)
            )
        )
    ).scalars().all()
    assert pre == []

    stats = await seed_platform_templates(db_session, dry_run=False)
    await db_session.commit()

    assert stats.inspected == 16
    assert stats.created == 16
    assert stats.skipped == 0

    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.company_id.is_(None)
            )
        )
    ).scalars().all()
    assert len(rows) == 16

    # Cover every (kind, lang) pair exactly once.
    pairs = {(row.kind, row.language) for row in rows}
    expected = {(kind, lang) for kind in KINDS for lang in LANGS}
    assert pairs == expected

    for row in rows:
        assert row.status == TemplateStatus.ACTIVE
        assert row.version == 1
        assert row.created_by is None
        assert row.asset_files == ["logo.png", "signature.png", "stamp.png"]
        assert row.storage_prefix == f"_platform/templates/{row.kind}/{row.language}/"


@pytest.mark.asyncio
async def test_seed_is_idempotent(
    db_session: AsyncSession,
) -> None:
    """Second run after a successful first run is a no-op."""
    first = await seed_platform_templates(db_session, dry_run=False)
    await db_session.commit()
    assert first.created == 16
    assert first.skipped == 0

    second = await seed_platform_templates(db_session, dry_run=False)
    await db_session.commit()
    assert second.inspected == 16
    assert second.created == 0
    assert second.skipped == 16

    # Row count unchanged -- exactly 16 active platform defaults.
    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.company_id.is_(None),
                CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
            )
        )
    ).scalars().all()
    assert len(rows) == 16
