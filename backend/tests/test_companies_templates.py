# =============================================================================
# CBSHOME Backend -- Document Templates Tests (Refactor 2 iter 2.3)
# =============================================================================
#
# Coverage:
#   find_active_template (4-stage fallback, R2 §4.7):
#     1. per-company / user-lang
#     2. per-company / en
#     3. platform-default / user-lang
#     4. platform-default / en
#
#   Redis cache (R2 §4.10):
#     - get_template_html_cached returns bytes from MinIO on miss
#     - subsequent calls hit Redis (asserted by changing MinIO bytes)
#     - invalidate_template_html_cache forces a re-fetch
#
#   Staff endpoints (R2 §4.5):
#     - GET /staff/companies/{id}/templates returns per-company rows
#       merged with platform-default fallbacks for uncovered (kind, lang)
#     - GET /staff/companies/{id}/templates/{tpl_id} returns html_content
#     - kind / language / status filters apply
#     - is_platform_default flag derived from company_id
#
# Email prefix: "tplr_" -- unique to this test file.
#
# NOTE on platform defaults:
#   These tests assume the 16 platform-default rows from `cbshome seed`
#   exist in the DB (company_id IS NULL, kind/lang covering all 4 x 4
#   combinations). The tests do NOT delete them; tests that need to
#   exercise specific stages of the fallback create per-company rows
#   and let the platform defaults sit untouched as the next-stage match.
# =============================================================================

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
    upload_object,
)
from app.modules.companies.constants import (
    DocumentTemplateKind,
    TemplateStatus,
)
from app.modules.companies.models import CompanyDocumentTemplate
from app.modules.companies.service import (
    find_active_template,
    get_template_html_cached,
    invalidate_template_html_cache,
)
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
)

EMAIL_PREFIX = "tplr_"
TEST_BUCKET = "cbshome-attachments-test"
VALID_DIST_CONFIG = {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}


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
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


@pytest.fixture(autouse=True)
async def clear_template_cache() -> AsyncGenerator[None, None]:
    """Drop any leftover template_html:* keys before each test.

    The cache is keyed on storage_prefix; tests that switch between
    MinIO bytes for the same prefix would otherwise see stale cache
    from a previous test.
    """
    try:
        redis = get_redis()
        keys = await redis.keys("template_html:*")
        if keys:
            await redis.delete(*keys)
    except RuntimeError:
        # Redis not initialized yet (rare -- only on session startup).
        pass
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_and_company(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[User, str, UUID]:
    """Create admin staff + one company; return (staff_user, admin_token, company_id)."""
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
            "name": "Templates Test Co",
            "price_per_unit_cents": 10000,
            "distribution_config": VALID_DIST_CONFIG,
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    company_id = UUID(resp.json()["id"])
    return staff_user, admin_token, company_id


async def _insert_template_row(
    db_session: AsyncSession,
    *,
    company_id: UUID | None,
    kind: DocumentTemplateKind | str,
    language: str,
    version: int = 1,
    status: TemplateStatus | str = TemplateStatus.ACTIVE,
    storage_prefix: str | None = None,
    asset_files: list[str] | None = None,
    title: str | None = None,
    created_by: UUID | None = None,
) -> CompanyDocumentTemplate:
    """Insert a CompanyDocumentTemplate row directly via the session.

    No service wrapper exists yet (per-company upload goes through
    reconcile, R2 §4.5 read-only MVP), so tests that need a row in a
    specific shape use this helper.
    """
    if storage_prefix is None:
        if company_id is None:
            storage_prefix = f"_platform/templates/{kind}/{language}/"
        else:
            storage_prefix = f"companies/{company_id}/templates/{kind}/{language}/"
    if asset_files is None:
        asset_files = ["logo.png", "signature.png", "stamp.png"]
    if title is None:
        title = f"Test {kind} {language} v{version}"

    row = CompanyDocumentTemplate(
        company_id=company_id,
        kind=str(kind),
        language=language,
        version=version,
        title=title,
        storage_prefix=storage_prefix,
        asset_files=asset_files,
        status=str(status),
        created_by=created_by,
    )
    db_session.add(row)
    await db_session.commit()
    return row


# ---------------------------------------------------------------------------
# find_active_template -- 4-stage fallback (R2 §4.7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_active_template_stage_1_per_company_user_lang(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stage 1: per-company row in user_lang wins over everything else.

    Setup deliberately stocks every other stage so a wrong picker would
    return the wrong row instead of failing closed.
    """
    _, _, company_id = await _admin_and_company(client, db_session)
    expected = await _insert_template_row(
        db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="de",
    )
    # Stage 2 alternative -- should not be picked.
    await _insert_template_row(
        db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="en",
    )
    # Platform defaults are already in the DB from `cbshome seed` (16 rows).

    found = await find_active_template(
        session=db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="de",
    )
    assert found is not None
    assert found.id == expected.id
    assert found.company_id == company_id
    assert found.language == "de"


@pytest.mark.asyncio
async def test_find_active_template_stage_2_per_company_en_fallback(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stage 2: no per-company de -> falls back to per-company en."""
    _, _, company_id = await _admin_and_company(client, db_session)
    expected = await _insert_template_row(
        db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="en",
    )

    found = await find_active_template(
        session=db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="de",
    )
    assert found is not None
    assert found.id == expected.id
    assert found.company_id == company_id
    assert found.language == "en"


@pytest.mark.asyncio
async def test_find_active_template_stage_3_platform_user_lang(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stage 3: no per-company rows for the kind -> platform default user_lang."""
    _, _, company_id = await _admin_and_company(client, db_session)
    # No per-company rows; platform defaults (from `cbshome seed`) cover
    # all kinds and languages.

    found = await find_active_template(
        session=db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="ru",
    )
    assert found is not None
    assert found.company_id is None  # platform default
    assert found.language == "ru"
    assert found.kind == DocumentTemplateKind.PURCHASE_AGREEMENT


@pytest.mark.asyncio
async def test_find_active_template_stage_4_platform_en_fallback(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stage 4: no platform default for the requested language -> platform en.

    The 4 platform-default languages from `cbshome seed` include en/ru/de/ar.
    Asking for `fr` triggers stage 4 (only platform en is available for fr).
    """
    _, _, company_id = await _admin_and_company(client, db_session)

    found = await find_active_template(
        session=db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="fr",
    )
    assert found is not None
    assert found.company_id is None  # platform default
    assert found.language == "en"
    assert found.kind == DocumentTemplateKind.PURCHASE_AGREEMENT


# ---------------------------------------------------------------------------
# Redis cache (R2 §4.10)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_template_html_cache_hit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Second read returns cached bytes even when MinIO content has changed."""
    _, _, company_id = await _admin_and_company(client, db_session)
    storage_prefix = f"companies/{company_id}/templates/purchase_agreement/en/"

    original = b"<html>v1</html>"
    await upload_object(
        storage_prefix + "template.html", original, "text/html; charset=utf-8"
    )

    first = await get_template_html_cached(storage_prefix)
    assert first == original.decode("utf-8")

    # Replace MinIO bytes; cache should still return v1.
    await upload_object(
        storage_prefix + "template.html",
        b"<html>v2-NEW</html>",
        "text/html; charset=utf-8",
    )
    second = await get_template_html_cached(storage_prefix)
    assert second == original.decode("utf-8")


@pytest.mark.asyncio
async def test_template_html_cache_invalidate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """invalidate_template_html_cache forces a re-fetch from MinIO."""
    _, _, company_id = await _admin_and_company(client, db_session)
    storage_prefix = f"companies/{company_id}/templates/purchase_agreement/en/"

    await upload_object(
        storage_prefix + "template.html",
        b"<html>v1</html>",
        "text/html; charset=utf-8",
    )
    await get_template_html_cached(storage_prefix)  # warms cache

    await upload_object(
        storage_prefix + "template.html",
        b"<html>v2-NEW</html>",
        "text/html; charset=utf-8",
    )
    await invalidate_template_html_cache(storage_prefix)

    fresh = await get_template_html_cached(storage_prefix)
    assert fresh == "<html>v2-NEW</html>"


# ---------------------------------------------------------------------------
# Staff endpoints (R2 §4.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_list_merges_per_company_and_platform(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """list returns per-company rows + platform fallbacks for uncovered pairs.

    The company has ONE per-company override (purchase_agreement / en).
    The list response must include that row PLUS one platform-default row
    per (kind, lang) pair NOT covered by an active per-company row.
    """
    _, admin_token, company_id = await _admin_and_company(client, db_session)
    own = await _insert_template_row(
        db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="en",
    )

    resp = await client.get(
        f"/api/v1/staff/companies/{company_id}/templates",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()

    own_items = [i for i in items if i["id"] == str(own.id)]
    assert len(own_items) == 1
    assert own_items[0]["is_platform_default"] is False
    assert own_items[0]["company_id"] == str(company_id)

    # The platform-default row for (purchase_agreement, en) must NOT
    # appear -- the company already has its own active for that pair.
    pa_en_platform = [
        i for i in items
        if i["kind"] == "purchase_agreement"
        and i["language"] == "en"
        and i["is_platform_default"] is True
    ]
    assert pa_en_platform == []

    # Other (kind, lang) pairs MUST come through as platform defaults.
    pa_de_platform = [
        i for i in items
        if i["kind"] == "purchase_agreement"
        and i["language"] == "de"
        and i["is_platform_default"] is True
    ]
    assert len(pa_de_platform) == 1
    assert pa_de_platform[0]["company_id"] is None


@pytest.mark.asyncio
async def test_staff_list_filter_by_kind_and_language(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """kind + language filters narrow the merged listing."""
    _, admin_token, company_id = await _admin_and_company(client, db_session)

    resp = await client.get(
        f"/api/v1/staff/companies/{company_id}/templates",
        params={"kind": "purchase_agreement", "language": "ru"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) >= 1
    for item in items:
        assert item["kind"] == "purchase_agreement"
        assert item["language"] == "ru"


@pytest.mark.asyncio
async def test_staff_list_status_archived_excludes_platform_defaults(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Filtering by non-active status drops platform defaults entirely.

    Platform defaults only exist as active rows in the seed; asking for
    archived/draft must return only per-company rows in those states.
    """
    _, admin_token, company_id = await _admin_and_company(client, db_session)
    archived = await _insert_template_row(
        db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="en",
        version=1,
        status=TemplateStatus.ARCHIVED,
    )

    resp = await client.get(
        f"/api/v1/staff/companies/{company_id}/templates",
        params={"status": "archived"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["id"] == str(archived.id)
    assert items[0]["is_platform_default"] is False


@pytest.mark.asyncio
async def test_staff_detail_returns_html_content(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Detail endpoint inlines html_content from MinIO via the cached helper."""
    _, admin_token, company_id = await _admin_and_company(client, db_session)
    template = await _insert_template_row(
        db_session,
        company_id=company_id,
        kind=DocumentTemplateKind.PURCHASE_AGREEMENT,
        language="en",
    )

    body = b"<html><body>hello purchase agreement</body></html>"
    await upload_object(
        template.storage_prefix + "template.html",
        body,
        "text/html; charset=utf-8",
    )

    resp = await client.get(
        f"/api/v1/staff/companies/{company_id}/templates/{template.id}",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["id"] == str(template.id)
    assert payload["html_content"] == body.decode("utf-8")
    assert payload["storage_prefix"] == template.storage_prefix
    assert payload["is_platform_default"] is False
    assert payload["asset_files"] == ["logo.png", "signature.png", "stamp.png"]
