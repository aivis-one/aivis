# =============================================================================
# CBSHOME Backend -- seed_platform_templates Tests (iter 2.5 mini-fix #3)
# =============================================================================
#
# WHAT IS UNDER TEST:
#   scripts/seed_platform_templates.py -- the script that puts the 16
#   platform-default CompanyDocumentTemplate rows (4 kinds x 4 languages,
#   company_id IS NULL, status=active) into the DB.
#
# KEY PROPERTY THAT BROKE LAST TIME:
#   Earlier the script hardcoded version=1, so on a re-run against a DB
#   where the same (kind, lang) pair already had an archived row with
#   version=1, the INSERT collided on UNIQUE NULLS NOT DISTINCT
#   (company_id, kind, language, version) and the seed transaction died.
#   The current script computes version = max(version across all
#   statuses) + 1, recovering automatically. T3 and T4 verify that.
#
# WORKER-DB CONTRACT:
#   The template DB ships with all 16 active rows already seeded. To
#   test seed behaviour we wipe the platform-default rows (company_id
#   IS NULL) before every scenario in this file. The wipe is safe --
#   the worker DB disappears at session end and no other test file
#   sees this state.
# =============================================================================

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.modules.companies.constants import DocumentTemplateKind, TemplateStatus
from app.modules.companies.models import CompanyDocumentTemplate
from scripts.seed_platform_templates import seed_platform_templates


# Constants that match the script's domain (4 kinds x 4 languages = 16 pairs).
EXPECTED_KINDS = {
    DocumentTemplateKind.PURCHASE_AGREEMENT,
    DocumentTemplateKind.OWNERSHIP_CERTIFICATE,
    DocumentTemplateKind.GIFT_CERTIFICATE,
    DocumentTemplateKind.INSTALLMENT_SUBCONTRACT,
}
EXPECTED_LANGUAGES = {"en", "ru", "de", "ar"}
EXPECTED_PAIR_COUNT = len(EXPECTED_KINDS) * len(EXPECTED_LANGUAGES)  # 16

# A specific pair used by the recovery scenarios. Choice is arbitrary --
# (purchase_agreement, en) is the pair that historically broke in prod,
# which is poetic but not load-bearing.
RECOVERY_KIND = DocumentTemplateKind.PURCHASE_AGREEMENT
RECOVERY_LANG = "en"


# ---------------------------------------------------------------------------
# Per-scenario reset: wipe platform-default rows + the audit rows the
# seed script emits. Worker DB is ephemeral, but other test files in this
# worker run AFTER this module; they expect the same 16 seeded rows that
# the template DB ships with. So the teardown re-seeds before yielding
# control back to the next module.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def wipe_platform_state(
    db_session: AsyncSession,
) -> AsyncGenerator[None, None]:
    """Delete all platform-default templates and seed-audit rows so every
    scenario starts from a known empty baseline. On teardown, restore the
    16 seeded rows so the worker DB looks like a fresh clone again.
    """
    # Pre-test wipe.
    await db_session.execute(
        delete(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.company_id.is_(None)
        )
    )
    await db_session.execute(
        delete(AuditLog).where(AuditLog.event == "platform.template_seeded")
    )
    await db_session.commit()
    yield

    # Post-test restore. Wipe whatever the test left behind (it might have
    # produced 0 rows, 16 rows, or something in between), then call the
    # real seed function to put the canonical 16 rows back. The audit
    # rows the restore emits are removed too -- only the canonical seed
    # state should leak out of this module.
    await db_session.execute(
        delete(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.company_id.is_(None)
        )
    )
    await db_session.execute(
        delete(AuditLog).where(AuditLog.event == "platform.template_seeded")
    )
    await db_session.commit()
    await seed_platform_templates(db_session)
    await db_session.execute(
        delete(AuditLog).where(AuditLog.event == "platform.template_seeded")
    )
    await db_session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _count_active_platform_rows(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count(CompanyDocumentTemplate.id)).where(
            and_(
                CompanyDocumentTemplate.company_id.is_(None),
                CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
            )
        )
    )
    return result.scalar_one()


async def _count_seed_audit_rows(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.event == "platform.template_seeded"
        )
    )
    return result.scalar_one()


async def _insert_archived_row(
    session: AsyncSession,
    *,
    kind: DocumentTemplateKind,
    language: str,
    version: int,
) -> None:
    """Manually insert one archived platform-default row. Used by the
    recovery scenarios to simulate the broken-DB state the seed must
    heal from.
    """
    row = CompanyDocumentTemplate(
        company_id=None,
        kind=kind,
        language=language,
        version=version,
        status=TemplateStatus.ARCHIVED,
        title=f"Archived test row v{version}",
        storage_prefix=(
            f"_platform/templates-archive/{kind.value}/{language}/v{version}"
        ),
        created_by=None,
        created_at=datetime.now(timezone.utc),
        archived_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.commit()


async def _fetch_active_row(
    session: AsyncSession,
    *,
    kind: DocumentTemplateKind,
    language: str,
) -> CompanyDocumentTemplate | None:
    result = await session.execute(
        select(CompanyDocumentTemplate).where(
            and_(
                CompanyDocumentTemplate.company_id.is_(None),
                CompanyDocumentTemplate.kind == kind,
                CompanyDocumentTemplate.language == language,
                CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
            )
        )
    )
    return result.scalar_one_or_none()


async def _fetch_seed_audit_for_pair(
    session: AsyncSession,
    *,
    kind: DocumentTemplateKind,
    language: str,
) -> AuditLog | None:
    """Find the platform.template_seeded audit row whose `data` matches
    the given (kind, language). The script writes one audit row per
    pair it seeds.
    """
    result = await session.execute(
        select(AuditLog).where(AuditLog.event == "platform.template_seeded")
    )
    for row in result.scalars().all():
        data = row.data or {}
        if data.get("kind") == kind.value and data.get("language") == language:
            return row
    return None


# ---------------------------------------------------------------------------
# T1 -- fresh seed creates all 16 active rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_seed_creates_16_active(db_session: AsyncSession) -> None:
    """Empty platform-defaults -> seed creates one active row per
    (kind, language) pair at version=1.
    """
    stats = await seed_platform_templates(db_session)
    await db_session.commit()

    assert stats.created == EXPECTED_PAIR_COUNT
    assert stats.skipped == 0

    assert await _count_active_platform_rows(db_session) == EXPECTED_PAIR_COUNT

    # Exhaustive check: every (kind, lang) pair has exactly one v=1 active row.
    for kind in EXPECTED_KINDS:
        for lang in EXPECTED_LANGUAGES:
            row = await _fetch_active_row(db_session, kind=kind, language=lang)
            assert row is not None, f"missing active row for ({kind}, {lang})"
            assert row.version == 1, (
                f"({kind}, {lang}) seeded at v{row.version}, expected v1"
            )


# ---------------------------------------------------------------------------
# T2 -- idempotent skip when fully seeded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotent_skip_on_full_seeded(
    db_session: AsyncSession,
) -> None:
    """After a fresh seed, running seed_platform_templates again must
    skip all 16 pairs and write zero new audit rows.

    The "no new audit rows" check enforces the no-spam contract: idempotent
    re-runs (which `cbshome update` will trigger) must not pollute
    audit_log with `platform.template_seeded` heartbeats.
    """
    # Setup: first seed populates all 16 pairs + emits 16 audit rows.
    first = await seed_platform_templates(db_session)
    await db_session.commit()
    assert first.created == EXPECTED_PAIR_COUNT

    audit_before = await _count_seed_audit_rows(db_session)
    assert audit_before == EXPECTED_PAIR_COUNT

    # Act: second seed should be a no-op.
    second = await seed_platform_templates(db_session)
    await db_session.commit()

    assert second.created == 0
    assert second.skipped == EXPECTED_PAIR_COUNT

    # Critical: audit_log unchanged.
    audit_after = await _count_seed_audit_rows(db_session)
    assert audit_after == audit_before, (
        "idempotent seed must NOT write platform.template_seeded "
        f"audit rows (before: {audit_before}, after: {audit_after})"
    )


# ---------------------------------------------------------------------------
# T3 -- recovery from a single archived row (the historical breakage)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_from_archived_only(db_session: AsyncSession) -> None:
    """Simulate the broken state from prod:
        - 15 pairs empty,
        - 1 pair (RECOVERY_KIND, RECOVERY_LANG) has ONLY an archived v=1 row.

    The seed script must:
        1. Create a fresh active row for the broken pair at v=2 (NOT v=1,
           which would collide on UNIQUE NULLS NOT DISTINCT).
        2. Mark the audit row for that pair with recovered_from_archived=True
           and max_archived_version=1.
        3. Treat the other 15 pairs as a normal fresh seed.
    """
    # Setup: one archived row for the recovery pair.
    await _insert_archived_row(
        db_session,
        kind=RECOVERY_KIND,
        language=RECOVERY_LANG,
        version=1,
    )

    # Act.
    stats = await seed_platform_templates(db_session)
    await db_session.commit()

    assert stats.created == EXPECTED_PAIR_COUNT
    assert stats.skipped == 0

    # Active row for the recovery pair must be at version=2.
    recovery_row = await _fetch_active_row(
        db_session, kind=RECOVERY_KIND, language=RECOVERY_LANG
    )
    assert recovery_row is not None
    assert recovery_row.version == 2, (
        f"recovery pair created at v{recovery_row.version}, "
        "expected v2 (one past max archived)"
    )

    # Audit row for the recovery pair must flag the recovery.
    audit = await _fetch_seed_audit_for_pair(
        db_session, kind=RECOVERY_KIND, language=RECOVERY_LANG
    )
    assert audit is not None
    data = audit.data or {}
    assert data.get("recovered_from_archived") is True, (
        f"recovery audit missing recovered_from_archived flag: {data}"
    )
    assert data.get("max_archived_version") == 1, (
        f"recovery audit max_archived_version={data.get('max_archived_version')}, "
        "expected 1"
    )

    # Sanity: the other 15 pairs are normal v=1 active rows without the flag.
    for kind in EXPECTED_KINDS:
        for lang in EXPECTED_LANGUAGES:
            if kind == RECOVERY_KIND and lang == RECOVERY_LANG:
                continue
            row = await _fetch_active_row(db_session, kind=kind, language=lang)
            assert row is not None
            assert row.version == 1


# ---------------------------------------------------------------------------
# T4 -- recovery with multiple archived rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_with_multiple_archived(
    db_session: AsyncSession,
) -> None:
    """Two archived rows for the same pair (v1 and v2). Seed must pick
    max+1 = v3 and record max_archived_version=2 in the audit row.
    """
    await _insert_archived_row(
        db_session, kind=RECOVERY_KIND, language=RECOVERY_LANG, version=1
    )
    await _insert_archived_row(
        db_session, kind=RECOVERY_KIND, language=RECOVERY_LANG, version=2
    )

    stats = await seed_platform_templates(db_session)
    await db_session.commit()

    assert stats.created == EXPECTED_PAIR_COUNT

    row = await _fetch_active_row(
        db_session, kind=RECOVERY_KIND, language=RECOVERY_LANG
    )
    assert row is not None
    assert row.version == 3

    audit = await _fetch_seed_audit_for_pair(
        db_session, kind=RECOVERY_KIND, language=RECOVERY_LANG
    )
    assert audit is not None
    data = audit.data or {}
    assert data.get("recovered_from_archived") is True
    assert data.get("max_archived_version") == 2


# ---------------------------------------------------------------------------
# T5 -- dry run writes nothing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_no_writes(db_session: AsyncSession) -> None:
    """In dry-run mode the script reports what it WOULD do but performs
    no INSERTs and emits no audit rows.
    """
    stats = await seed_platform_templates(db_session, dry_run=True)
    await db_session.commit()

    # would-be created = full 16 (since we wiped in fixture).
    assert stats.created == EXPECTED_PAIR_COUNT
    assert stats.skipped == 0

    # No actual rows in the DB.
    assert await _count_active_platform_rows(db_session) == 0
    assert await _count_seed_audit_rows(db_session) == 0
