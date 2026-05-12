# =============================================================================
# CBSHOME Backend -- Seed Platform Default Templates Tests
#                     (iter 2.5 mini-fix #2 rewrite)
# =============================================================================
#
# Tests cover the idempotency contract of `seed_platform_templates`:
# - Running seed on a DB that already has the 16 active platform-default
#   rows must produce zero creates (inspected=16, skipped=16, created=0).
# - Whatever state the DB is in on entry, after the test the DB has at
#   least one active platform-default row per (kind, language) pair --
#   later tests in the same session can rely on platform defaults
#   existing.
#
# NO DESTRUCTIVE FIXTURE:
#   The previous version of this file wiped `company_document_templates
#   WHERE company_id IS NULL` in setup. That cascaded via FK SET NULL
#   onto purchases.purchase_agreement_template_id and orphaned Purchase
#   rows seeded by other tests (iter 2.5 mini-fix #2 root cause).
#
#   The replacement does NOT delete anything. seed_platform_templates is
#   idempotent by contract; we just invoke it twice and assert on the
#   stats.
#
# Email prefix: "seedp_"
# =============================================================================

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.constants import (
    DocumentTemplateKind,
    TemplateStatus,
)
from app.modules.companies.models import CompanyDocumentTemplate
from scripts.seed_platform_templates import (
    LANGUAGES,
    seed_platform_templates,
)


EXPECTED_PAIR_COUNT = len(DocumentTemplateKind) * len(LANGUAGES)


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_covers_every_pair(
    db_session: AsyncSession,
) -> None:
    """After at most one run, every (kind, language) pair has an active
    platform-default row; a second run is a no-op."""
    # First run -- creates whatever is still missing. If the dev DB
    # already has all 16 (e.g. another test seeded them earlier in the
    # session), this is a pure skip. Either way, after the commit every
    # pair is covered.
    first = await seed_platform_templates(db_session, dry_run=False)
    await db_session.commit()

    assert first.inspected == EXPECTED_PAIR_COUNT
    assert first.created + first.skipped == EXPECTED_PAIR_COUNT

    # Second run on the same session -- every pair already covered, so
    # the call must report skipped == 16 and create nothing.
    second = await seed_platform_templates(db_session, dry_run=False)
    await db_session.commit()

    assert second.inspected == EXPECTED_PAIR_COUNT
    assert second.created == 0
    assert second.skipped == EXPECTED_PAIR_COUNT

    # Verify coverage at the row level. Exactly one active row per
    # (kind, language) pair must exist with company_id IS NULL.
    stmt = select(
        CompanyDocumentTemplate.kind,
        CompanyDocumentTemplate.language,
    ).where(
        CompanyDocumentTemplate.company_id.is_(None),
        CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
    )
    rows = (await db_session.execute(stmt)).all()
    pairs = {(row.kind, row.language) for row in rows}

    expected_pairs = {
        (kind, lang)
        for kind in DocumentTemplateKind
        for lang in LANGUAGES
    }
    assert pairs == expected_pairs


@pytest.mark.asyncio
async def test_seed_dry_run_does_not_write(
    db_session: AsyncSession,
) -> None:
    """`dry_run=True` reports what *would* happen but never inserts.

    Pre-state matters here: we run a real seed first so the dry-run
    has nothing to do, then assert that the dry-run reports zero
    actions. This avoids relying on a "clean DB" assumption (the
    previous file deleted rows in setup to get one).
    """
    # Make sure the DB is in the fully-seeded state.
    await seed_platform_templates(db_session, dry_run=False)
    await db_session.commit()

    # Row count BEFORE the dry-run.
    count_stmt = select(CompanyDocumentTemplate).where(
        CompanyDocumentTemplate.company_id.is_(None)
    )
    rows_before = (await db_session.execute(count_stmt)).scalars().all()

    dry = await seed_platform_templates(db_session, dry_run=True)
    # Dry-run reports `created` for would-be inserts. Since DB is fully
    # seeded, it must be zero across the board.
    assert dry.inspected == EXPECTED_PAIR_COUNT
    assert dry.created == 0
    assert dry.skipped == EXPECTED_PAIR_COUNT

    # Row count AFTER -- unchanged.
    rows_after = (await db_session.execute(count_stmt)).scalars().all()
    assert len(rows_after) == len(rows_before)
