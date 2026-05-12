# =============================================================================
# CBSHOME Backend -- Reconcile Platform Templates Tests
#                     (iter 2.5 mini-fix #2 rewrite)
# =============================================================================
#
# Tests cover two reconcile_platform_templates outcomes:
#   1. fresh inbox folder -> CREATE a new active row (version=1).
#   2. inbox folder for an already-active pair -> archive the previous
#      active row and CREATE a new active with version+1.
#
# ISOLATION:
#   Uses a dedicated test bucket via monkeypatch so the live DEV bucket
#   (`cbshome-attachments`) is never touched. The bucket is drained
#   between tests. NO platform-default DB rows are deleted -- the bug
#   the previous version of this file caused was rooted in that DELETE
#   cascading via FK SET NULL onto purchases.purchase_agreement_template_id.
#
#   To exercise the "archive previous" branch we use a SYNTHETIC kind
#   that doesn't exist in DocumentTemplateKind... no, wait: the inbox
#   folder name must use a real DocumentTemplateKind value, otherwise
#   sidecar validation fails. So instead we use the real
#   purchase_agreement / en pair, accept that an active row may already
#   exist for it (seeded by other tests), and assert on RELATIVE state
#   changes rather than absolute counts.
#
# Email prefix: "rcnp_"
# =============================================================================

import json
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import func, select
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
from scripts.reconcile_platform_templates import (
    INBOX_PREFIX,
    reconcile_platform_templates,
)


TEST_BUCKET = "cbshome-attachments-test"
DEFAULTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "templates"
    / "_default"
)
HTML_NAME = "template.html"
SIDECAR_NAME = "_meta.cbsmeta.json"
ASSET_FILES = ("logo.png", "signature.png", "stamp.png")


@pytest.fixture
async def isolated_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[None, None]:
    """Point storage at the test bucket and drain it on entry and exit.

    Scoped to function -- each test gets a clean bucket and any leftover
    keys from a crashed test do not bleed across.
    """
    monkeypatch.setattr(settings, "minio_bucket", TEST_BUCKET)

    async def _drain() -> None:
        keys = await list_objects("")
        for key in keys:
            await delete_object(key)

    await _drain()
    try:
        yield
    finally:
        await _drain()


async def _upload_inbox_folder(
    *,
    kind: str,
    language: str,
    status: str,
    title: str,
) -> None:
    """Lay out a complete inbox folder in the active (test) bucket.

    Files come from `backend/scripts/templates/_default/<kind>/<lang>/`
    so we know the HTML passes the placeholder validator.
    """
    src_dir = DEFAULTS_DIR / kind / language
    folder_key = f"{INBOX_PREFIX}{kind}__{language}/"

    # template.html -- raw bytes, no rewriting.
    html_bytes = (src_dir / HTML_NAME).read_bytes()
    await upload_object(
        folder_key + HTML_NAME,
        html_bytes,
        "text/html; charset=utf-8",
    )

    # Asset PNGs.
    for asset in ASSET_FILES:
        asset_bytes = (src_dir / asset).read_bytes()
        await upload_object(
            folder_key + asset,
            asset_bytes,
            "image/png",
        )

    # Sidecar metadata. Schema: TemplateInboxMetadata in
    # app/modules/companies/schemas.py -- four required fields
    # (kind, language, title, status) all strings, extra="forbid".
    sidecar = {
        "kind": kind,
        "language": language,
        "title": title,
        "status": status,
    }
    await upload_object(
        folder_key + SIDECAR_NAME,
        json.dumps(sidecar).encode("utf-8"),
        "application/json",
    )


async def _count_rows_for_pair(
    session: AsyncSession,
    *,
    kind: str,
    language: str,
    status: TemplateStatus | None = None,
) -> int:
    """Count platform-default rows (company_id IS NULL) for one pair.

    Optionally filtered by status. Used in assertions to express
    relative changes that don't depend on what other tests left
    behind.
    """
    stmt = select(func.count(CompanyDocumentTemplate.id)).where(
        CompanyDocumentTemplate.company_id.is_(None),
        CompanyDocumentTemplate.kind == kind,
        CompanyDocumentTemplate.language == language,
    )
    if status is not None:
        stmt = stmt.where(CompanyDocumentTemplate.status == status)
    return (await session.execute(stmt)).scalar_one()


@pytest.mark.asyncio
async def test_reconcile_archives_previous_active_and_bumps_version(
    isolated_bucket: None,
    db_session: AsyncSession,
) -> None:
    """An inbox folder for an existing active pair archives the previous
    active row and creates a fresh active with version+1.

    Pre-state: at least one active row for (purchase_agreement, en) is
    assumed (every dev DB has it after `cbshome update`). The test does
    NOT assert how many archived rows exist before -- only the delta.
    """
    KIND = DocumentTemplateKind.PURCHASE_AGREEMENT.value
    LANG = "en"

    # Snapshot before.
    active_before = await _count_rows_for_pair(
        db_session, kind=KIND, language=LANG, status=TemplateStatus.ACTIVE
    )
    archived_before = await _count_rows_for_pair(
        db_session, kind=KIND, language=LANG, status=TemplateStatus.ARCHIVED
    )
    max_version_stmt = select(
        func.max(CompanyDocumentTemplate.version)
    ).where(
        CompanyDocumentTemplate.company_id.is_(None),
        CompanyDocumentTemplate.kind == KIND,
        CompanyDocumentTemplate.language == LANG,
    )
    max_version_before = (
        (await db_session.execute(max_version_stmt)).scalar() or 0
    )

    # Sanity: the seed step in `cbshome update` guarantees an active
    # row for every (kind, language) pair. If this is zero we'd be
    # testing the "fresh CREATE" branch instead, which is covered by
    # the next test.
    assert active_before >= 1, (
        "Test assumes a pre-existing active platform-default row for "
        "(purchase_agreement, en). Run `cbshome update` first."
    )

    # Drop a fresh inbox folder.
    await _upload_inbox_folder(
        kind=KIND,
        language=LANG,
        status="active",
        title="rcnp_ archive-and-replace test",
    )

    stats = await reconcile_platform_templates(db_session, dry_run=False)

    # The reconcile call commits per folder internally, so no commit
    # needed here.
    assert stats.archived_and_replaced >= 1, (
        f"Expected at least one archived_and_replaced outcome, got "
        f"stats={stats!r}"
    )

    # Active count unchanged (one archived, one created).
    active_after = await _count_rows_for_pair(
        db_session, kind=KIND, language=LANG, status=TemplateStatus.ACTIVE
    )
    assert active_after == active_before

    # Archived count increased by exactly one.
    archived_after = await _count_rows_for_pair(
        db_session, kind=KIND, language=LANG, status=TemplateStatus.ARCHIVED
    )
    assert archived_after == archived_before + 1

    # Version of new active is max_version_before + 1.
    new_active_stmt = select(CompanyDocumentTemplate).where(
        CompanyDocumentTemplate.company_id.is_(None),
        CompanyDocumentTemplate.kind == KIND,
        CompanyDocumentTemplate.language == LANG,
        CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
    )
    new_active = (
        await db_session.execute(new_active_stmt)
    ).scalar_one()
    assert new_active.version == max_version_before + 1


@pytest.mark.asyncio
async def test_reconcile_skips_inbox_folder_with_bad_sidecar(
    isolated_bucket: None,
    db_session: AsyncSession,
) -> None:
    """Inbox folder whose sidecar JSON declares a kind that does not
    match the folder name is rejected with status="skipped"."""
    KIND = DocumentTemplateKind.PURCHASE_AGREEMENT.value
    LANG = "en"

    # Snapshot version BEFORE so we can assert no insertion happened.
    max_version_stmt = select(
        func.max(CompanyDocumentTemplate.version)
    ).where(
        CompanyDocumentTemplate.company_id.is_(None),
        CompanyDocumentTemplate.kind == KIND,
        CompanyDocumentTemplate.language == LANG,
    )
    max_version_before = (
        (await db_session.execute(max_version_stmt)).scalar() or 0
    )

    # Upload an inbox folder whose folder name says purchase_agreement
    # but whose sidecar says gift_certificate -- mismatch -> skip.
    folder_key = f"{INBOX_PREFIX}{KIND}__{LANG}/"
    html_bytes = (DEFAULTS_DIR / KIND / LANG / HTML_NAME).read_bytes()
    await upload_object(
        folder_key + HTML_NAME, html_bytes, "text/html; charset=utf-8"
    )
    for asset in ASSET_FILES:
        await upload_object(
            folder_key + asset,
            (DEFAULTS_DIR / KIND / LANG / asset).read_bytes(),
            "image/png",
        )
    bad_sidecar = {
        "kind": DocumentTemplateKind.GIFT_CERTIFICATE.value,  # wrong!
        "language": LANG,
        "title": "rcnp_ bad-sidecar test",
        "status": "active",
    }
    await upload_object(
        folder_key + SIDECAR_NAME,
        json.dumps(bad_sidecar).encode("utf-8"),
        "application/json",
    )

    stats = await reconcile_platform_templates(db_session, dry_run=False)

    assert stats.skipped >= 1, (
        f"Expected at least one skip for the bad-sidecar folder, "
        f"got stats={stats!r}"
    )
    assert stats.created == 0
    assert stats.archived_and_replaced == 0

    # Version unchanged -- nothing was inserted.
    max_version_after = (
        (await db_session.execute(max_version_stmt)).scalar() or 0
    )
    assert max_version_after == max_version_before
