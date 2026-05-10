# =============================================================================
# CBSHOME Backend -- Reconcile Platform Templates Tests
#                     (Refactor 2 iter 2.3, R2 §4.9)
# =============================================================================
#
# Same shape as test_reconcile_templates.py but on the platform inbox
# (`_platform/templates-inbox/`) producing rows with company_id IS NULL.
#
# Coverage:
#   - orphan inbox folder -> CREATE new active row, version=1, company_id NULL.
#   - replacement -> archive + new active version+1.
#   - bad sidecar -> SKIP + reason.
#   - dry-run -> no DB or MinIO writes.
#
# ISOLATION:
#   Same setup/teardown as test_seed_platform_templates.py:
#     setup    -- wipe platform-default rows + MinIO _platform/ in test bucket.
#     teardown -- re-upload bootstrap files + run seed_platform_templates so
#                 the shared DB and the next consumer see the canonical
#                 16-row state.
#
# Email prefix: "rcnp_" (no test users registered, kept for consistency).
# =============================================================================

import json
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import (
    delete_object,
    list_objects,
    object_exists,
    upload_object,
)
from app.modules.companies.constants import (
    DocumentTemplateKind,
    TemplateStatus,
)
from app.modules.companies.models import CompanyDocumentTemplate
from scripts.reconcile_platform_templates import (
    CANONICAL_PREFIX_TEMPLATE,
    INBOX_PREFIX,
    reconcile_platform_templates,
)
from scripts.seed_platform_templates import seed_platform_templates

EMAIL_PREFIX = "rcnp_"
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

SEED_DIR = Path(__file__).resolve().parent.parent / "scripts" / "templates" / "_default"

VALID_HTML = (
    "<html><body>"
    "<img src=\"{{ asset_data_uri('logo.png') }}\">"
    "<img src=\"{{ asset_data_uri('signature.png') }}\">"
    "<img src=\"{{ asset_data_uri('stamp.png') }}\">"
    "</body></html>"
)


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
    """SETUP: wipe platform-default rows + MinIO _platform/ in test bucket.
    TEARDOWN: re-upload bootstrap files + re-run seed so subsequent tests
    in the session see the canonical 16-row state."""
    await db_session.execute(
        delete(CompanyDocumentTemplate).where(
            CompanyDocumentTemplate.company_id.is_(None)
        )
    )
    await db_session.commit()

    platform_keys = await list_objects("_platform/")
    for key in platform_keys:
        await delete_object(key)

    yield

    # Restore.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_inbox_folder(
    *,
    kind: str,
    language: str,
    html: str | None = VALID_HTML,
    sidecar: dict | None = None,
    sidecar_raw: bytes | None = None,
    assets: dict[str, bytes] | None = None,
) -> dict[str, str]:
    """Place template.html + sidecar + assets into one platform inbox folder."""
    folder = f"{kind}__{language}/"
    keys: dict[str, str] = {}

    if html is not None:
        key = INBOX_PREFIX + folder + "template.html"
        await upload_object(key, html.encode("utf-8"), "text/html; charset=utf-8")
        keys["template.html"] = key

    if sidecar_raw is not None:
        key = INBOX_PREFIX + folder + "_meta.cbsmeta.json"
        await upload_object(key, sidecar_raw, "application/json")
        keys["_meta.cbsmeta.json"] = key
    elif sidecar is not None:
        key = INBOX_PREFIX + folder + "_meta.cbsmeta.json"
        await upload_object(
            key, json.dumps(sidecar).encode("utf-8"), "application/json"
        )
        keys["_meta.cbsmeta.json"] = key

    if assets is None:
        assets = {
            "logo.png": b"\x89PNG\r\n\x1a\n",
            "signature.png": b"\x89PNG\r\n\x1a\n",
            "stamp.png": b"\x89PNG\r\n\x1a\n",
        }
    for filename, content in assets.items():
        key = INBOX_PREFIX + folder + filename
        await upload_object(key, content, "image/png")
        keys[filename] = key

    return keys


def _default_sidecar(kind: str, language: str, title: str = "Platform Title") -> dict:
    return {
        "kind": kind,
        "language": language,
        "title": title,
        "status": "active",
    }


# ---------------------------------------------------------------------------
# 1: orphan -> create platform-default row (company_id IS NULL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orphan_creates_platform_default_row(
    db_session: AsyncSession,
) -> None:
    """Setup wiped rows; reconcile from a fresh platform inbox creates v1."""
    keys = await _seed_inbox_folder(
        kind="purchase_agreement",
        language="de",
        sidecar=_default_sidecar("purchase_agreement", "de", "Platform PA DE v1"),
    )

    stats = await reconcile_platform_templates(db_session)

    assert stats.inspected == 1
    assert stats.created == 1
    assert stats.archived_and_replaced == 0
    assert stats.skipped == 0

    for key in keys.values():
        assert await object_exists(key) is False

    canonical = CANONICAL_PREFIX_TEMPLATE.format(
        kind="purchase_agreement", language="de"
    )
    assert await object_exists(canonical + "template.html") is True
    assert await object_exists(canonical + "logo.png") is True

    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.company_id.is_(None),
                CompanyDocumentTemplate.kind == DocumentTemplateKind.PURCHASE_AGREEMENT,
                CompanyDocumentTemplate.language == "de",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.company_id is None
    assert row.status == TemplateStatus.ACTIVE
    assert row.version == 1
    assert row.title == "Platform PA DE v1"
    assert row.storage_prefix == canonical
    assert row.created_by is None


# ---------------------------------------------------------------------------
# 2: replacement -> archive previous, create new with version+1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replacement_archives_previous_and_bumps_version(
    db_session: AsyncSession,
) -> None:
    # First pass -- creates v1.
    await _seed_inbox_folder(
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en", "Platform PA EN v1"),
    )
    first = await reconcile_platform_templates(db_session)
    assert first.created == 1

    # Second pass -- replaces v1 with v2.
    await _seed_inbox_folder(
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en", "Platform PA EN v2"),
    )
    second = await reconcile_platform_templates(db_session)

    assert second.created == 0
    assert second.archived_and_replaced == 1
    assert second.skipped == 0

    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate)
            .where(
                CompanyDocumentTemplate.company_id.is_(None),
                CompanyDocumentTemplate.kind == DocumentTemplateKind.PURCHASE_AGREEMENT,
                CompanyDocumentTemplate.language == "en",
            )
            .order_by(CompanyDocumentTemplate.version)
        )
    ).scalars().all()
    assert len(rows) == 2
    archived, active = rows
    assert archived.version == 1
    assert archived.status == TemplateStatus.ARCHIVED
    assert active.version == 2
    assert active.status == TemplateStatus.ACTIVE
    assert active.title == "Platform PA EN v2"


# ---------------------------------------------------------------------------
# 3: bad sidecar -> skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_sidecar_is_skipped(
    db_session: AsyncSession,
) -> None:
    await _seed_inbox_folder(
        kind="purchase_agreement",
        language="en",
        sidecar_raw=b"{not valid json",
    )

    stats = await reconcile_platform_templates(db_session)

    assert stats.skipped == 1
    assert any("invalid sidecar" in r for r in stats.skipped_reasons)

    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.company_id.is_(None),
            )
        )
    ).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# 4: dry-run -> no DB or MinIO writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_makes_no_changes(
    db_session: AsyncSession,
) -> None:
    keys = await _seed_inbox_folder(
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en"),
    )

    stats = await reconcile_platform_templates(db_session, dry_run=True)

    assert stats.inspected == 1
    assert stats.created == 1  # would-be action, reported but not committed
    assert stats.skipped == 0

    for key in keys.values():
        assert await object_exists(key) is True

    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.company_id.is_(None),
            )
        )
    ).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# 5: draft status creates draft row WITHOUT archiving previous active (BUG-NEW-01)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_status_creates_draft_without_touching_active(
    db_session: AsyncSession,
) -> None:
    """sidecar status=draft inserts a draft platform-default row alongside
    the active v1 -- the active is left alone."""
    # Land active v1 first.
    await _seed_inbox_folder(
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en", "Platform PA EN v1"),
    )
    await reconcile_platform_templates(db_session)

    # Upload a draft.
    await _seed_inbox_folder(
        kind="purchase_agreement",
        language="en",
        sidecar={
            "kind": "purchase_agreement",
            "language": "en",
            "title": "Platform PA EN v2 draft",
            "status": "draft",
        },
    )
    stats = await reconcile_platform_templates(db_session)

    assert stats.created == 0
    assert stats.created_draft == 1
    assert stats.archived_and_replaced == 0
    assert stats.skipped == 0

    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate)
            .where(
                CompanyDocumentTemplate.company_id.is_(None),
                CompanyDocumentTemplate.kind == DocumentTemplateKind.PURCHASE_AGREEMENT,
                CompanyDocumentTemplate.language == "en",
            )
            .order_by(CompanyDocumentTemplate.version)
        )
    ).scalars().all()
    assert len(rows) == 2

    active, draft = rows
    assert active.version == 1
    assert active.status == TemplateStatus.ACTIVE
    assert draft.version == 2
    assert draft.status == TemplateStatus.DRAFT


# ---------------------------------------------------------------------------
# 6: dry-run reflects archived outcome correctly (BUG-NEW-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_reports_archived_outcome_when_active_exists(
    db_session: AsyncSession,
) -> None:
    """Dry-run after a real first pass reports archived_and_replaced."""
    await _seed_inbox_folder(
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en"),
    )
    first = await reconcile_platform_templates(db_session)
    assert first.created == 1

    await _seed_inbox_folder(
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en", "Platform PA EN v2"),
    )
    stats = await reconcile_platform_templates(db_session, dry_run=True)

    assert stats.created == 0
    assert stats.archived_and_replaced == 1
    assert stats.created_draft == 0
    assert stats.skipped == 0
