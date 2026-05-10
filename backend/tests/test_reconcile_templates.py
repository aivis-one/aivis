# =============================================================================
# CBSHOME Backend -- Reconcile Per-Company Templates Tests
#                     (Refactor 2 iter 2.3, R2 §4.8)
# =============================================================================
#
# Tests reconcile_company_templates() directly with a test AsyncSession,
# mirroring the pattern in test_reconcile_attachments.py. CLI plumbing is
# trivial; the interesting logic is the async helper.
#
# Coverage:
#   - orphan inbox folder -> CREATE new active row, version=1.
#   - replacement -> archive previous active, create new active with version+1.
#   - bad jinja syntax -> SKIP + reason.
#   - asset_data_uri references missing file -> SKIP + reason.
#   - bad sidecar (invalid JSON / fails Pydantic) -> SKIP + reason.
#   - dry-run -> no DB or MinIO writes.
#   - cache invalidation -> Redis template_html:* dropped on success.
#
# Email prefix: "rcnt_" -- distinct from tplr_ / seedp_ / rcnp_.
# =============================================================================

import json
from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import get_redis
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
from app.modules.companies.service import get_template_html_cached
from app.modules.users.models import User
from scripts.reconcile_templates import (
    CANONICAL_PREFIX_TEMPLATE,
    INBOX_PREFIX_TEMPLATE,
    reconcile_company_templates,
)
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
)

EMAIL_PREFIX = "rcnt_"
TEST_BUCKET = "cbshome-attachments-test"
VALID_DIST_CONFIG = {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}

# Minimal valid HTML (no Jinja vars beyond the universal asset_data_uri
# reference). Lets us exercise the whole reconcile pipeline without
# carrying the full TEMPLATE_PLACEHOLDERS surface in this test file.
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
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users (and their templates / companies / pools / ...) via
    cleanup_test_users (which now knows about CompanyDocumentTemplate)."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


@pytest.fixture(autouse=True)
async def clear_template_cache() -> AsyncGenerator[None, None]:
    """Drop any leftover template_html:* keys before each test."""
    try:
        redis = get_redis()
        keys = await redis.keys("template_html:*")
        if keys:
            await redis.delete(*keys)
    except RuntimeError:
        pass
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_and_company(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[User, UUID]:
    """Create admin staff + one company; return (staff_user, company_id)."""
    data, admin_token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    user_id = UUID(data["user"]["id"])
    staff_user = await db_session.get(User, user_id)
    assert staff_user is not None

    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"{EMAIL_PREFIX}co@example.com",
            "password": "companypass123",
            "name": "Reconcile Templates Co",
            "price_per_unit_cents": 10000,
            "distribution_config": VALID_DIST_CONFIG,
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return staff_user, UUID(resp.json()["id"])


async def _seed_inbox_folder(
    company_id: UUID,
    *,
    kind: str,
    language: str,
    html: str | None = VALID_HTML,
    sidecar: dict | None = None,
    sidecar_raw: bytes | None = None,
    assets: dict[str, bytes] | None = None,
    extra_files: dict[str, bytes] | None = None,
) -> dict[str, str]:
    """Place template.html + sidecar + assets into one inbox folder.

    Returns a {filename: full_minio_key} map so tests can check
    individual file presence after reconcile.

    `sidecar_raw` overrides `sidecar` and is uploaded as-is (used by
    the bad-JSON test). `extra_files` lets a test inject stray files
    that should make reconcile reject the folder.
    """
    inbox_prefix = INBOX_PREFIX_TEMPLATE.format(company_id=company_id)
    folder = f"{kind}__{language}/"
    keys: dict[str, str] = {}

    if html is not None:
        key = inbox_prefix + folder + "template.html"
        await upload_object(key, html.encode("utf-8"), "text/html; charset=utf-8")
        keys["template.html"] = key

    if sidecar_raw is not None:
        key = inbox_prefix + folder + "_meta.cbsmeta.json"
        await upload_object(key, sidecar_raw, "application/json")
        keys["_meta.cbsmeta.json"] = key
    elif sidecar is not None:
        key = inbox_prefix + folder + "_meta.cbsmeta.json"
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
        key = inbox_prefix + folder + filename
        await upload_object(key, content, "image/png")
        keys[filename] = key

    if extra_files:
        for filename, content in extra_files.items():
            key = inbox_prefix + folder + filename
            await upload_object(key, content, "application/octet-stream")
            keys[filename] = key

    return keys


def _default_sidecar(kind: str, language: str, title: str = "Test Title") -> dict:
    return {
        "kind": kind,
        "language": language,
        "title": title,
        "status": "active",
    }


# ---------------------------------------------------------------------------
# 1: orphan -> create new active, version=1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orphan_inbox_creates_new_active(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, company_id = await _admin_and_company(client, db_session)
    keys = await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="de",
        sidecar=_default_sidecar("purchase_agreement", "de", "PA DE v1"),
    )

    stats = await reconcile_company_templates(db_session, company_id)

    assert stats.inspected == 1
    assert stats.created == 1
    assert stats.archived_and_replaced == 0
    assert stats.skipped == 0

    # Inbox cleaned (template.html + assets moved, sidecar deleted).
    for key in keys.values():
        assert await object_exists(key) is False

    # Files at canonical path.
    canonical = CANONICAL_PREFIX_TEMPLATE.format(
        company_id=company_id, kind="purchase_agreement", language="de"
    )
    assert await object_exists(canonical + "template.html") is True
    assert await object_exists(canonical + "logo.png") is True
    assert await object_exists(canonical + "signature.png") is True
    assert await object_exists(canonical + "stamp.png") is True

    # New active row exists.
    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.company_id == company_id,
                CompanyDocumentTemplate.kind == DocumentTemplateKind.PURCHASE_AGREEMENT,
                CompanyDocumentTemplate.language == "de",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == TemplateStatus.ACTIVE
    assert row.version == 1
    assert row.title == "PA DE v1"
    assert row.storage_prefix == canonical
    assert sorted(row.asset_files) == ["logo.png", "signature.png", "stamp.png"]


# ---------------------------------------------------------------------------
# 2: replacement -> archive previous, create new with version+1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replacement_archives_previous_and_bumps_version(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, company_id = await _admin_and_company(client, db_session)
    # First pass -- creates v1.
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en", "PA EN v1"),
    )
    first = await reconcile_company_templates(db_session, company_id)
    assert first.created == 1

    # Second pass -- replaces v1 with v2.
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en", "PA EN v2"),
    )
    second = await reconcile_company_templates(db_session, company_id)

    assert second.inspected == 1
    assert second.created == 0
    assert second.archived_and_replaced == 1
    assert second.skipped == 0

    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate)
            .where(
                CompanyDocumentTemplate.company_id == company_id,
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
    assert active.title == "PA EN v2"


# ---------------------------------------------------------------------------
# 3: bad jinja syntax -> skip + reason
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bad_jinja_syntax_is_skipped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, company_id = await _admin_and_company(client, db_session)
    bad_html = "<html>{% if broken %}</html>"  # unclosed `{% if %}`
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        html=bad_html,
        sidecar=_default_sidecar("purchase_agreement", "en"),
    )

    stats = await reconcile_company_templates(db_session, company_id)

    assert stats.inspected == 1
    assert stats.created == 0
    assert stats.skipped == 1
    assert any("jinja2 parse error" in r for r in stats.skipped_reasons)

    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.company_id == company_id
            )
        )
    ).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# 4: asset_data_uri references missing file -> skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_asset_reference_is_skipped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, company_id = await _admin_and_company(client, db_session)
    html = (
        "<html>"
        "<img src=\"{{ asset_data_uri('logo.png') }}\">"
        "<img src=\"{{ asset_data_uri('NOT_THERE.png') }}\">"
        "</html>"
    )
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        html=html,
        sidecar=_default_sidecar("purchase_agreement", "en"),
        # Only logo.png provided -- the NOT_THERE.png reference points
        # at a file the folder doesn't contain.
        assets={"logo.png": b"\x89PNG\r\n\x1a\n"},
    )

    stats = await reconcile_company_templates(db_session, company_id)

    assert stats.skipped == 1
    assert any("missing assets" in r for r in stats.skipped_reasons)


# ---------------------------------------------------------------------------
# 5: bad sidecar (invalid JSON) -> skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_sidecar_json_is_skipped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, company_id = await _admin_and_company(client, db_session)
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        sidecar_raw=b"{not valid json",
    )

    stats = await reconcile_company_templates(db_session, company_id)

    assert stats.skipped == 1
    assert any("invalid sidecar" in r for r in stats.skipped_reasons)


# ---------------------------------------------------------------------------
# 6: folder name mismatch with sidecar kind/language -> skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_folder_kind_lang_mismatch_is_skipped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, company_id = await _admin_and_company(client, db_session)
    # Folder says purchase_agreement / en, sidecar disagrees.
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        sidecar={
            "kind": "gift_certificate",
            "language": "en",
            "title": "Drift",
            "status": "active",
        },
    )

    stats = await reconcile_company_templates(db_session, company_id)

    assert stats.skipped == 1
    assert any("folder kind" in r for r in stats.skipped_reasons)


# ---------------------------------------------------------------------------
# 7: dry-run -> no DB or MinIO writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_makes_no_changes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, company_id = await _admin_and_company(client, db_session)
    keys = await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en"),
    )

    stats = await reconcile_company_templates(db_session, company_id, dry_run=True)

    assert stats.inspected == 1
    assert stats.created == 1  # would-be action, reported but not committed
    assert stats.skipped == 0

    # Inbox files untouched.
    for key in keys.values():
        assert await object_exists(key) is True

    # No DB row.
    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.company_id == company_id
            )
        )
    ).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# 8: cache invalidation on successful replace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replace_invalidates_html_cache(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """After replace, cached HTML for the canonical prefix is dropped so
    the next render fetches fresh bytes from MinIO."""
    _, company_id = await _admin_and_company(client, db_session)

    # First pass to land an active v1.
    v1_html = "<html><body>v1 {{ asset_data_uri('logo.png') }}</body></html>"
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        html=v1_html,
        sidecar=_default_sidecar("purchase_agreement", "en"),
    )
    await reconcile_company_templates(db_session, company_id)

    canonical = CANONICAL_PREFIX_TEMPLATE.format(
        company_id=company_id, kind="purchase_agreement", language="en"
    )

    # Warm the cache with v1.
    cached = await get_template_html_cached(canonical)
    assert "v1" in cached

    # Second pass replaces canonical bytes with v2 + bumps DB row.
    v2_html = "<html><body>v2 {{ asset_data_uri('logo.png') }}</body></html>"
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        html=v2_html,
        sidecar=_default_sidecar("purchase_agreement", "en", "PA EN v2"),
    )
    second = await reconcile_company_templates(db_session, company_id)
    assert second.archived_and_replaced == 1

    # Cache must be invalidated -- next read returns v2.
    fresh = await get_template_html_cached(canonical)
    assert "v2" in fresh
    assert "v1" not in fresh


# ---------------------------------------------------------------------------
# 9: draft status creates draft row WITHOUT archiving previous active (BUG-NEW-01)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_status_creates_draft_without_touching_active(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """sidecar status=draft inserts a draft row alongside the active v1.

    The previous active is NOT archived -- the operator stages a candidate
    that find_active_template will skip (it filters on status=active),
    so production rendering keeps using v1 until a follow-up reconcile
    with status=active flips the page.
    """
    _, company_id = await _admin_and_company(client, db_session)

    # Land an active v1 first.
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en", "PA EN v1 active"),
    )
    await reconcile_company_templates(db_session, company_id)

    # Now upload a draft.
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        sidecar={
            "kind": "purchase_agreement",
            "language": "en",
            "title": "PA EN v2 draft",
            "status": "draft",
        },
    )
    stats = await reconcile_company_templates(db_session, company_id)

    assert stats.inspected == 1
    assert stats.created == 0
    assert stats.created_draft == 1
    assert stats.archived_and_replaced == 0
    assert stats.skipped == 0

    rows = (
        await db_session.execute(
            select(CompanyDocumentTemplate)
            .where(
                CompanyDocumentTemplate.company_id == company_id,
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
    assert active.title == "PA EN v1 active"
    assert draft.version == 2
    assert draft.status == TemplateStatus.DRAFT
    assert draft.title == "PA EN v2 draft"


# ---------------------------------------------------------------------------
# 10: dry-run outcome reflects what real run WOULD do (BUG-NEW-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_reports_archived_outcome_when_active_exists(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """When an active row exists, dry-run reports archived_and_replaced,
    not "created" -- the previous tautology is fixed."""
    _, company_id = await _admin_and_company(client, db_session)

    # Real first pass to land v1 active.
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en"),
    )
    first = await reconcile_company_templates(db_session, company_id)
    assert first.created == 1

    # Second pass in dry-run mode: outcome must be archived_and_replaced.
    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en", "PA EN v2"),
    )
    stats = await reconcile_company_templates(db_session, company_id, dry_run=True)

    assert stats.inspected == 1
    assert stats.created == 0
    assert stats.archived_and_replaced == 1
    assert stats.created_draft == 0
    assert stats.skipped == 0


# ---------------------------------------------------------------------------
# 11: created_by attribution -- BUG-NEW-03 fix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_created_by_is_platform_user_for_per_company_reconcile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Per-company reconcile rows attribute created_by to the platform
    user (system actor), not NULL. This matches the audit actor and
    keeps the FK referencing a real user.
    """
    from app.modules.auth.service import get_platform_user_id

    _, company_id = await _admin_and_company(client, db_session)
    platform_user_id = await get_platform_user_id(db_session)

    await _seed_inbox_folder(
        company_id,
        kind="purchase_agreement",
        language="en",
        sidecar=_default_sidecar("purchase_agreement", "en"),
    )
    await reconcile_company_templates(db_session, company_id)

    row = (
        await db_session.execute(
            select(CompanyDocumentTemplate).where(
                CompanyDocumentTemplate.company_id == company_id
            )
        )
    ).scalar_one()
    assert row.created_by == platform_user_id
