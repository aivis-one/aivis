# =============================================================================
# AIVIS.ONE Backend -- project pictures in our storage (H36 P-131)
# =============================================================================
#
# A project's logo, its dark logo, its cover and a product's cover are files
# in our storage. The rows hold the object key; every answer carries a
# presigned link signed from it, with the PUBLIC TTL on every surface; the
# documents carry the logo's bytes inline, never a link.
#
# What is pinned here:
#   1. the schema: the URL columns are gone AND the key columns exist;
#   2. upload / replace / remove for staff and for the project itself, the
#      key layout under companies/<id>/, the audit rows;
#   3. the product cover, and a product of another project answering 404;
#   4. the refusals: type, size per slot, empty file, unknown slot, the old
#      URL fields in every body, a bad extension handed to the service;
#   5. the links on every surface (staff, cabinet, storefront, product,
#      dashboard, portfolio) with the public TTL, and a signing failure
#      answered as "no picture";
#   6. documents: the logo inline as a data: URI, fetched only when the
#      template reads it, None when the object is gone.
#
# Axes:
#   REPEAT    -- the same slot uploaded twice (same and other extension);
#                the two logos side by side; one object behind six surfaces
#   EMPTINESS -- a project with no pictures (all links null); removing an
#                empty slot; an empty file; a template without the logo
#   SHORTAGE  -- a key whose object is gone; a signing failure; another
#                project's product; a logo over its 1 MiB limit while the
#                same bytes pass as a cover
#
# Most of these talk to the real storage of the test environment (RustFS),
# like test_storage_links.py. Signing alone needs no storage (it is a
# computation), so 1, the empty-project half of 5 and the refusals that
# stop before the upload would pass without it; everything that uploads
# or reads bytes needs it.
# =============================================================================

import base64
import io
import uuid
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.core.storage import StorageError, object_exists, upload_object
from app.modules.companies import media as media_module
from app.modules.companies.constants import (
    COMPANY_LOGO_MAX_BYTES,
    CompanyMediaSlot,
)
from app.modules.companies.media import company_logo_data_uri
from app.modules.companies.models import CompanyProfile
from app.modules.companies.service import set_company_media
from app.modules.dashboard.service import get_dashboard_summary
from app.modules.portfolio.service import get_company_position, get_portfolio
from app.modules.products.models import Product
from app.modules.purchases.agreement_service import (
    load_agreement_data,
    render_agreement_html,
)
from app.modules.purchases.document_utils import (
    build_document_environment,
    template_references,
)
from app.modules.users.models import User
from tests.helpers import auth_headers, create_admin_user, login_user
from tests.test_regression_guards import (
    _create_company_with_product,
    _create_investor_and_purchase,
)

# A valid 1x1 PNG.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4c500"
    "00000049454e44ae426082"
)
# Not a real WEBP; the type is taken from the extension, the bytes only
# have to come back as they went in.
_WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 fake"

_PUBLIC_TTL = str(settings.storage_presigned_ttl_public)


def _ttl(url: str) -> str:
    return parse_qs(urlsplit(url).query)["X-Amz-Expires"][0]


def _key_of(url: str) -> str:
    """The object key a link points at (path after the bucket)."""
    path = urlsplit(url).path
    return path.split(f"/{settings.storage_bucket}/", 1)[1]


async def _get(url: str) -> httpx.Response:
    async with httpx.AsyncClient() as http:
        return await http.get(url)


def _ip() -> dict[str, str]:
    return {"X-Real-IP": f"198.51.100.{uuid.uuid4().int % 200 + 20}"}


async def _company(
    client: AsyncClient, admin_token: str
) -> tuple[str, str, str]:
    """A fresh project -> (company_id, its owner's user id, its session token)."""
    email = f"media_{uuid.uuid4().hex[:12]}@example.com"
    password = "companypass123"
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": password,
            "name": f"MediaCo {uuid.uuid4().hex[:8]}",
            "price_per_unit_cents": 10_000,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    token = (await login_user(client, email=email, password=password))[
        "session_token"
    ]
    return body["id"], body["user_id"], token


async def _key(db_session: AsyncSession, company_id: str, column: str) -> str | None:
    db_session.expire_all()
    row = await db_session.get(CompanyProfile, UUID(company_id))
    return getattr(row, column)


# ---------------------------------------------------------------------------
# 1: the schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_url_columns_are_gone_and_the_key_columns_exist(
    db_session: AsyncSession,
) -> None:
    """Paired: the old columns are absent AND the new ones are present -- an
    absence alone would also pass on a table that lost everything."""
    rows = (
        await db_session.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_name IN ('company_profiles', 'products')"
            )
        )
    ).all()
    columns = {(t, c) for t, c in rows}
    for gone in (
        ("company_profiles", "logo_url"),
        ("company_profiles", "cover_url"),
        ("products", "cover_url"),
    ):
        assert gone not in columns
    for present in (
        ("company_profiles", "logo_storage_key"),
        ("company_profiles", "logo_dark_storage_key"),
        ("company_profiles", "cover_storage_key"),
        ("products", "cover_storage_key"),
        # Untouched by H36.
        ("company_profiles", "promo_video_url"),
        ("company_profiles", "presentation_url"),
    ):
        assert present in columns


# ---------------------------------------------------------------------------
# 2: upload, replace, remove
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_project_without_pictures_has_null_links_everywhere(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """EMPTINESS: nothing uploaded -> every link is null, for staff and for
    the project itself; removing an empty slot is a 404, not a no-op."""
    _, admin_token = await create_admin_user(client, db_session)
    company_id, _, token = await _company(client, admin_token)

    staff = await client.get(
        f"/api/v1/staff/companies/{company_id}", headers=auth_headers(admin_token)
    )
    own = await client.get("/api/v1/companies/me", headers=auth_headers(token))
    for resp in (staff, own):
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["logo_url"] is None
        assert body["logo_dark_url"] is None
        assert body["cover_url"] is None

    for slot in ("logo", "logo-dark", "cover"):
        resp = await client.delete(
            f"/api/v1/staff/companies/{company_id}/media/{slot}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404, (slot, resp.text)
        resp = await client.delete(
            f"/api/v1/companies/me/media/{slot}", headers=auth_headers(token)
        )
        assert resp.status_code == 404, (slot, resp.text)


@pytest.mark.asyncio
async def test_staff_uploads_replaces_and_removes_the_logo(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """REPEAT: the same extension overwrites the same key; another extension
    moves to a new key and deletes the old object. The link serves the bytes
    and carries the public TTL. Removal clears the key, deletes the object
    and is audited."""
    _, admin_token = await create_admin_user(client, db_session)
    company_id, _, _ = await _company(client, admin_token)
    url = f"/api/v1/staff/companies/{company_id}/media/logo"

    resp = await client.put(
        url, files={"file": ("logo.png", _PNG, "image/png")}, headers=auth_headers(admin_token)
    )
    assert resp.status_code == 200, resp.text
    link = resp.json()["logo_url"]
    assert link and _ttl(link) == _PUBLIC_TTL
    png_key = f"companies/{company_id}/media/logo.png"
    assert _key_of(link) == png_key
    assert await _key(db_session, company_id, "logo_storage_key") == png_key
    served = await _get(link)
    assert served.status_code == 200
    assert served.content == _PNG
    assert served.headers["content-type"] == "image/png"

    # Same extension: same key, new bytes.
    other_png = _PNG + b"\x00"
    resp = await client.put(
        url,
        files={"file": ("LOGO.PNG", other_png, "image/png")},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert await _key(db_session, company_id, "logo_storage_key") == png_key
    assert (await _get(resp.json()["logo_url"])).content == other_png

    # Another extension: new key, the old object is gone.
    resp = await client.put(
        url, files={"file": ("logo.webp", _WEBP, "image/webp")}, headers=auth_headers(admin_token)
    )
    assert resp.status_code == 200, resp.text
    webp_key = f"companies/{company_id}/media/logo.webp"
    assert await _key(db_session, company_id, "logo_storage_key") == webp_key
    assert await object_exists(webp_key)
    assert not await object_exists(png_key)

    # Remove.
    resp = await client.delete(url, headers=auth_headers(admin_token))
    assert resp.status_code == 204, resp.text
    assert await _key(db_session, company_id, "logo_storage_key") is None
    assert not await object_exists(webp_key)
    again = await client.delete(url, headers=auth_headers(admin_token))
    assert again.status_code == 404

    events = (
        await db_session.execute(
            select(AuditLog.event, AuditLog.actor_type).where(
                AuditLog.target_id == UUID(company_id),
                AuditLog.event.like("company.logo_%"),
            )
        )
    ).all()
    assert sorted(e for e, _ in events) == [
        "company.logo_deleted",
        "company.logo_uploaded",
        "company.logo_uploaded",
        "company.logo_uploaded",
    ]
    assert {a for _, a in events} == {"staff"}


@pytest.mark.asyncio
async def test_the_project_manages_its_own_pictures_and_the_slots_are_separate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """REPEAT: the logo and the dark logo are two keys; removing one leaves
    the other. The project's own uploads are audited as the user and show
    in its own change log."""
    _, admin_token = await create_admin_user(client, db_session)
    company_id, owner_id, token = await _company(client, admin_token)

    for slot, name in (("logo", "a.png"), ("logo-dark", "b.png"), ("cover", "c.jpg")):
        mime = "image/jpeg" if name.endswith(".jpg") else "image/png"
        resp = await client.put(
            f"/api/v1/companies/me/media/{slot}",
            files={"file": (name, _PNG, mime)},
            headers=auth_headers(token),
        )
        assert resp.status_code == 200, (slot, resp.text)

    body = (await client.get("/api/v1/companies/me", headers=auth_headers(token))).json()
    assert _key_of(body["logo_url"]) == f"companies/{company_id}/media/logo.png"
    assert _key_of(body["logo_dark_url"]) == f"companies/{company_id}/media/logo-dark.png"
    assert _key_of(body["cover_url"]) == f"companies/{company_id}/media/cover.jpg"
    for field in ("logo_url", "logo_dark_url", "cover_url"):
        assert _ttl(body[field]) == _PUBLIC_TTL

    resp = await client.delete("/api/v1/companies/me/media/logo", headers=auth_headers(token))
    assert resp.status_code == 204, resp.text
    body = (await client.get("/api/v1/companies/me", headers=auth_headers(token))).json()
    assert body["logo_url"] is None
    assert body["logo_dark_url"] is not None
    assert await object_exists(f"companies/{company_id}/media/logo-dark.png")

    events = (
        await db_session.execute(
            select(AuditLog.event, AuditLog.actor_type, AuditLog.actor_id).where(
                AuditLog.target_id == UUID(company_id),
                AuditLog.event.in_(
                    (
                        "company.logo_uploaded",
                        "company.logo_dark_uploaded",
                        "company.cover_uploaded",
                        "company.logo_deleted",
                    )
                ),
            )
        )
    ).all()
    assert len(events) == 4
    assert {(a, str(i)) for _, a, i in events} == {("user", owner_id)}

    feed = await client.get("/api/v1/company/audit", headers=auth_headers(token))
    assert feed.status_code == 200, feed.text
    feed_events = {row["event"] for row in feed.json()["items"]}
    assert {"company.logo_dark_uploaded", "company.logo_deleted"} <= feed_events


# ---------------------------------------------------------------------------
# 3: the product cover
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_uploads_and_removes_a_product_cover(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The cover lives under the project's prefix and reaches the staff
    list, the storefront list and the product page with the public TTL.
    A product of another project answers 404 and nothing is written."""
    _, admin_token = await create_admin_user(client, db_session)
    company, product = await _create_company_with_product(client, admin_token)
    other_company, other_product = await _create_company_with_product(client, admin_token)
    url = f"/api/v1/staff/companies/{company['id']}/products/{product['id']}/cover"

    # SHORTAGE: the right product under the wrong project.
    resp = await client.put(
        f"/api/v1/staff/companies/{company['id']}/products/{other_product['id']}/cover",
        files={"file": ("c.png", _PNG, "image/png")},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404, resp.text
    db_session.expire_all()
    assert (await db_session.get(Product, UUID(other_product["id"]))).cover_storage_key is None
    resp = await client.delete(
        f"/api/v1/staff/companies/{other_company['id']}/products/{product['id']}/cover",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404

    resp = await client.put(
        url, files={"file": ("c.png", _PNG, "image/png")}, headers=auth_headers(admin_token)
    )
    assert resp.status_code == 200, resp.text
    key = f"companies/{company['id']}/products/{product['id']}/cover.png"
    assert _key_of(resp.json()["cover_url"]) == key

    staff_list = await client.get(
        f"/api/v1/staff/companies/{company['id']}/products",
        headers=auth_headers(admin_token),
    )
    public_list = await client.get(
        f"/api/v1/public/products?company_id={company['id']}", headers=_ip()
    )
    public_one = await client.get(f"/api/v1/public/products/{product['id']}", headers=_ip())
    for resp, cover in (
        (staff_list, staff_list.json()["items"][0]["cover_url"]),
        (public_list, public_list.json()["items"][0]["cover_url"]),
        (public_one, public_one.json()["cover_url"]),
    ):
        assert resp.status_code == 200, resp.text
        assert _key_of(cover) == key
        assert _ttl(cover) == _PUBLIC_TTL

    resp = await client.delete(url, headers=auth_headers(admin_token))
    assert resp.status_code == 204, resp.text
    assert not await object_exists(key)
    assert (await client.delete(url, headers=auth_headers(admin_token))).status_code == 404
    public_one = await client.get(f"/api/v1/public/products/{product['id']}", headers=_ip())
    assert public_one.json()["cover_url"] is None

    events = (
        await db_session.execute(
            select(AuditLog.event).where(AuditLog.target_id == UUID(product["id"]))
        )
    ).scalars().all()
    assert "product.cover_uploaded" in events and "product.cover_deleted" in events


# ---------------------------------------------------------------------------
# 4: refusals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pictures_that_are_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SHORTAGE / EMPTINESS at the door: a type outside png/jpg/jpeg/webp,
    a file without an extension, an empty file, an unknown slot, a logo
    over 1 MiB. The SAME over-1-MiB bytes pass as a cover (its limit is
    10 MiB): the limit is the slot's, not the route's."""
    _, admin_token = await create_admin_user(client, db_session)
    company_id, _, token = await _company(client, admin_token)
    base = f"/api/v1/staff/companies/{company_id}/media"
    headers = auth_headers(admin_token)

    for name in ("logo.svg", "logo", "logo.gif"):
        resp = await client.put(
            f"{base}/logo", files={"file": (name, _PNG, "image/png")}, headers=headers
        )
        assert resp.status_code == 400, (name, resp.text)

    resp = await client.put(f"{base}/logo", files={"file": ("e.png", b"", "image/png")}, headers=headers)
    assert resp.status_code == 400, resp.text

    resp = await client.put(f"{base}/banner", files={"file": ("b.png", _PNG, "image/png")}, headers=headers)
    assert resp.status_code == 422, resp.text
    resp = await client.put(
        "/api/v1/companies/me/media/logo_dark",
        files={"file": ("b.png", _PNG, "image/png")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422, resp.text

    big = _PNG + b"\x00" * (COMPANY_LOGO_MAX_BYTES + 1 - len(_PNG))
    for slot in ("logo", "logo-dark"):
        resp = await client.put(
            f"{base}/{slot}", files={"file": ("big.png", big, "image/png")}, headers=headers
        )
        assert resp.status_code == 400, (slot, resp.text)
    assert await _key(db_session, company_id, "logo_storage_key") is None
    assert not await object_exists(f"companies/{company_id}/media/logo.png")

    resp = await client.put(f"{base}/cover", files={"file": ("big.png", big, "image/png")}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cover_url"]


@pytest.mark.asyncio
async def test_the_old_url_fields_are_refused_in_every_body(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No legacy: logo_url / cover_url in a create, assign, update or
    product body is a 422, not a silently ignored key."""
    _, admin_token = await create_admin_user(client, db_session)
    headers = auth_headers(admin_token)
    company, product = await _create_company_with_product(client, admin_token)

    for field in ("logo_url", "cover_url"):
        resp = await client.patch(
            f"/api/v1/staff/companies/{company['id']}",
            json={field: "https://example.com/x.png"},
            headers=headers,
        )
        assert resp.status_code == 422, (field, resp.text)
        resp = await client.post(
            "/api/v1/staff/companies",
            json={
                "email": f"old_{uuid.uuid4().hex[:10]}@example.com",
                "password": "companypass123",
                "name": "Old Fields Co",
                "price_per_unit_cents": 100,
                "distribution_config": {"company_pct": 0.65, "agent_levels": [0.1]},
                "total_supply": 1000,
                field: "https://example.com/x.png",
            },
            headers=headers,
        )
        assert resp.status_code == 422, (field, resp.text)
        resp = await client.post(
            "/api/v1/staff/companies/assign",
            json={
                "user_id": str(uuid.uuid4()),
                "name": "Old Fields Co",
                "price_per_unit_cents": 100,
                "distribution_config": {"company_pct": 0.65, "agent_levels": [0.1]},
                "total_supply": 1000,
                field: "https://example.com/x.png",
            },
            headers=headers,
        )
        assert resp.status_code == 422, (field, resp.text)

    resp = await client.patch(
        f"/api/v1/staff/products/{product['id']}",
        json={"cover_url": "https://example.com/x.png"},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company["id"],
            "name": "Old Fields Package",
            "package_size": 10,
            "cover_url": "https://example.com/x.png",
        },
        headers=headers,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_the_service_refuses_a_bad_extension_before_writing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The services are called directly too (H37's seeding): an extension
    without its dot, or a type that does not match it, is refused before
    the upload -- the extension becomes part of the key."""
    admin, admin_token = await create_admin_user(client, db_session)
    company_id, _, _ = await _company(client, admin_token)
    staff = await db_session.get(User, admin.id)

    for ext, mime in (("png", "image/png"), (".png", "image/jpeg"), (".svg", "image/svg+xml")):
        with pytest.raises(BadRequestError):
            await set_company_media(
                db_session,
                UUID(company_id),
                staff,
                slot=CompanyMediaSlot.LOGO,
                file_data=io.BytesIO(_PNG),
                file_size_bytes=len(_PNG),
                content_type=mime,
                file_extension=ext,
            )
    await db_session.rollback()
    assert await _key(db_session, company_id, "logo_storage_key") is None
    assert not await object_exists(f"companies/{company_id}/media/logopng")


# ---------------------------------------------------------------------------
# 5: the links on every surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_logo_reaches_every_surface_with_the_public_ttl(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """REPEAT: one object behind six surfaces, every one signed with the
    public TTL -- the cabinet's included, where a 15-minute link would break
    the header logo of a long-lived page."""
    _, admin_token = await create_admin_user(client, db_session)
    company, product = await _create_company_with_product(client, admin_token)
    company_id = company["id"]
    for slot in ("logo", "logo-dark"):
        resp = await client.put(
            f"/api/v1/staff/companies/{company_id}/media/{slot}",
            files={"file": ("l.png", _PNG, "image/png")},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200, resp.text
    inv_id, _sale_id = await _create_investor_and_purchase(client, db_session, product["id"])

    staff = (
        await client.get(f"/api/v1/staff/companies/{company_id}", headers=auth_headers(admin_token))
    ).json()
    public = (await client.get(f"/api/v1/public/companies/{company_id}", headers=_ip())).json()
    public_list = (await client.get("/api/v1/public/companies?per_page=100", headers=_ip())).json()
    listed = next(c for c in public_list["items"] if c["id"] == company_id)
    product_page = (await client.get(f"/api/v1/public/products/{product['id']}", headers=_ip())).json()
    dashboard = await get_dashboard_summary(inv_id, db_session)
    portfolio = await get_portfolio(inv_id, db_session)
    position = await get_company_position(inv_id, UUID(company_id), db_session)

    pairs = [
        (staff["logo_url"], staff["logo_dark_url"]),
        (public["logo_url"], public["logo_dark_url"]),
        (listed["logo_url"], listed["logo_dark_url"]),
        (product_page["company_logo_url"], product_page["company_logo_dark_url"]),
        (dashboard.companies[0].logo_url, dashboard.companies[0].logo_dark_url),
        (portfolio.positions[0].logo_url, portfolio.positions[0].logo_dark_url),
        (position.logo_url, position.logo_dark_url),
    ]
    for light, dark in pairs:
        assert _key_of(light) == f"companies/{company_id}/media/logo.png"
        assert _key_of(dark) == f"companies/{company_id}/media/logo-dark.png"
        assert _ttl(light) == _ttl(dark) == _PUBLIC_TTL


@pytest.mark.asyncio
async def test_a_signing_failure_is_no_picture_not_a_500(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SHORTAGE: the storage cannot sign -> 200 with null links."""
    _, admin_token = await create_admin_user(client, db_session)
    company_id, _, token = await _company(client, admin_token)
    resp = await client.put(
        f"/api/v1/staff/companies/{company_id}/media/cover",
        files={"file": ("c.png", _PNG, "image/png")},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["cover_url"]

    async def _refuse(_key: str, _ttl: int) -> str:
        raise StorageError("signing unavailable")

    monkeypatch.setattr(media_module, "generate_presigned_url", _refuse)
    resp = await client.get("/api/v1/companies/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["cover_url"] is None


# ---------------------------------------------------------------------------
# 6: documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_document_logo_is_inline_bytes_and_none_when_absent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The light logo as data:<mime>;base64 of the object's bytes; None
    without a key; None (not an error) when the key's object is gone."""
    _, admin_token = await create_admin_user(client, db_session)
    company_id, _, _ = await _company(client, admin_token)
    profile = await db_session.get(CompanyProfile, UUID(company_id))
    assert await company_logo_data_uri(profile) is None

    resp = await client.put(
        f"/api/v1/staff/companies/{company_id}/media/logo",
        files={"file": ("l.png", _PNG, "image/png")},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    await db_session.refresh(profile)
    uri = await company_logo_data_uri(profile)
    assert uri == "data:image/png;base64," + base64.b64encode(_PNG).decode("ascii")

    # A key whose object is gone.
    profile.logo_storage_key = f"companies/{company_id}/media/logo-missing.webp"
    assert await company_logo_data_uri(profile) is None
    await db_session.rollback()


def test_template_references_sees_only_the_variable_it_is_asked_about() -> None:
    env = build_document_environment(None)
    assert template_references(env, '<img src="{{ company_logo_url }}">', "company_logo_url")
    assert template_references(
        env, "{% if company_logo_url %}x{% endif %}", "company_logo_url"
    )
    assert not template_references(env, "{{ company_name }}", "company_logo_url")
    assert not template_references(env, "", "company_logo_url")


@pytest.mark.asyncio
async def test_the_agreement_inlines_the_logo_only_when_the_template_reads_it(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A template reading company_logo_url gets the bytes inline (no link
    to expire in a frozen agreement); a template that does not read it
    never fetches them."""
    _, admin_token = await create_admin_user(client, db_session)
    company, product = await _create_company_with_product(client, admin_token)
    resp = await client.put(
        f"/api/v1/staff/companies/{company['id']}/media/logo",
        files={"file": ("l.png", _PNG, "image/png")},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    inv_id, sale_id = await _create_investor_and_purchase(client, db_session, product["id"])

    async def _assets(_prefix: str, _files: list[str]):
        return lambda _name: ""

    monkeypatch.setattr(
        "app.modules.purchases.agreement_service.make_asset_data_uri_func", _assets
    )

    body = {"html": ""}

    async def _html(_prefix: str) -> str:
        return body["html"]

    monkeypatch.setattr(
        "app.modules.purchases.agreement_service.get_template_html_cached", _html
    )

    body["html"] = "{{ company_logo_url }}"
    data = await load_agreement_data(sale_id, inv_id, db_session)
    data.purchase.agreement_html = None
    rendered = await render_agreement_html(data, db_session)
    assert rendered == "data:image/png;base64," + base64.b64encode(_PNG).decode("ascii")
    assert "X-Amz" not in rendered

    fetched: list[str] = []

    async def _no_bytes(key: str) -> bytes:
        fetched.append(key)
        raise AssertionError("the logo must not be fetched")

    monkeypatch.setattr(media_module, "get_object_bytes", _no_bytes)
    body["html"] = "{{ company_name }}"
    rendered = await render_agreement_html(data, db_session)
    assert rendered == company["name"]
    assert fetched == []
