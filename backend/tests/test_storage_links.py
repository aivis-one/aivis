# =============================================================================
# AIVIS.ONE Backend -- links a browser opens (H32 P-121)
# =============================================================================
#
# Every file a person opens -- an attachment, a KYC document, a roadmap
# cover -- reaches the browser as a presigned link. Until H32 the links
# were signed for the INTERNAL storage address (http://minio:9000), which
# no browser can reach, with SigV2, whose signature does not cover the
# host; attachments came back as a 302 the frontend followed with fetch;
# and any roadmap item WITH a cover raised TypeError (the TTL was never
# passed) and answered 500.
#
# What is pinned here:
#   1. the link is SigV4 and signed for STORAGE_PUBLIC_URL; the storage
#      accepts it with that Host and refuses it with any other -- which
#      is the property the public storage site relies on;
#   2. with STORAGE_PUBLIC_URL empty (development) the link is signed for
#      the internal address, which the test runner reaches directly;
#   3. both attachment download endpoints return {url, ttl_seconds}, the
#      link carries Content-Disposition: attachment with the original
#      filename, and a file that may not be seen returns 404 and no link;
#   4. a roadmap item with a cover renders on every surface, with the TTL
#      of that surface (auth for staff and company, public for the
#      storefront), and the link serves the image.
#
# Axes:
#   REPEAT    -- the same object behind three surfaces, three TTLs
#   EMPTINESS -- no STORAGE_PUBLIC_URL; an item without a cover
#   SHORTAGE  -- a Host that is not the signed one; an unpublished or
#                non-public attachment
#
# These talk to the real storage of the test environment (RustFS on the
# box), like test_storage.py: a presigned link is only proven by using it.
# =============================================================================

import json
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import delete_object, generate_presigned_url, upload_object
from tests.helpers import auth_headers, create_admin_user, login_user

_PUBLIC = "https://files.storage-links.test"

# A valid 1x1 PNG: the cover endpoint derives the type from the filename,
# but the bytes should still be an image.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4c500"
    "00000049454e44ae426082"
)


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def _assert_sigv4(url: str, ttl: int) -> None:
    query = _query(url)
    assert query["X-Amz-Algorithm"] == "AWS4-HMAC-SHA256"
    assert query["X-Amz-Expires"] == str(ttl)
    assert query["X-Amz-Signature"]
    assert "host" in query["X-Amz-SignedHeaders"].split(";")
    # The SigV2 form must be gone, not merely joined by the SigV4 one.
    assert "AWSAccessKeyId" not in query
    assert "Signature" not in query


async def _fetch(url: str, host: str | None = None) -> httpx.Response:
    """GET the link from the storage's internal address.

    With `host`, the request carries that Host header -- what the public
    site forwards unchanged. The path and query are the link's own.
    """
    parts = urlsplit(url)
    target = settings.storage_endpoint.rstrip("/") + parts.path
    if parts.query:
        target += "?" + parts.query
    headers = {"Host": host} if host else {}
    async with httpx.AsyncClient() as http:
        return await http.get(target, headers=headers)


# ---------------------------------------------------------------------------
# 1-2: who the link is signed for
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_is_signed_for_the_public_host_and_only_works_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Signed for STORAGE_PUBLIC_URL with SigV4: the storage serves it to a
    request carrying that Host (what the public storage site forwards), and refuses
    the very same path and signature under the internal Host."""
    monkeypatch.setattr(settings, "storage_public_url", _PUBLIC)
    key = f"_tests/storage-links/{uuid.uuid4().hex}/public.txt"
    payload = b"signed for the public host"
    await upload_object(key, payload, "text/plain")
    try:
        url = await generate_presigned_url(key, ttl_seconds=60)

        assert url.startswith(f"{_PUBLIC}/{settings.storage_bucket}/{key}?")
        _assert_sigv4(url, 60)

        served = await _fetch(url, host=urlsplit(_PUBLIC).hostname)
        assert served.status_code == 200
        assert served.content == payload

        refused = await _fetch(url)
        assert refused.status_code == 403
    finally:
        await delete_object(key)


@pytest.mark.asyncio
async def test_link_without_a_public_url_is_signed_for_the_internal_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Development has no public site: an empty STORAGE_PUBLIC_URL signs
    for the internal address, and the link works there as it stands."""
    monkeypatch.setattr(settings, "storage_public_url", "")
    key = f"_tests/storage-links/{uuid.uuid4().hex}/internal.txt"
    await upload_object(key, b"internal", "text/plain")
    try:
        url = await generate_presigned_url(key, ttl_seconds=60)
        assert url.startswith(settings.storage_endpoint.rstrip("/") + "/")
        _assert_sigv4(url, 60)
        async with httpx.AsyncClient() as http:
            response = await http.get(url)
        assert response.status_code == 200
        assert response.content == b"internal"
    finally:
        await delete_object(key)


# ---------------------------------------------------------------------------
# 3: attachment downloads
# ---------------------------------------------------------------------------


async def _company_with_attachment(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    is_published: bool,
    is_public: bool,
    filename: str,
    content: bytes,
) -> tuple[str, str, str]:
    """Create a company and one attachment -> (company_id, attachment_id,
    company session token)."""
    _admin, admin_token = await create_admin_user(client, db_session)
    email = f"colinks_{uuid.uuid4().hex[:12]}@example.com"
    password = "companypass123"
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": password,
            "name": f"LinksCo {uuid.uuid4().hex[:8]}",
            "description": "Storage links test company",
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
    company_id = resp.json()["id"]
    token = (await login_user(client, email=email, password=password))[
        "session_token"
    ]

    resp = await client.post(
        "/api/v1/company/attachments",
        data={
            "metadata": json.dumps(
                {
                    "title": "Links test document",
                    "category": "legal/incorporation",
                    "order": 0,
                    "is_published": is_published,
                    "is_public": is_public,
                }
            )
        },
        files={"file": (filename, content, "application/pdf")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return company_id, resp.json()["id"], token


@pytest.mark.asyncio
async def test_attachment_downloads_return_a_link_that_downloads(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Both download endpoints answer {url, ttl_seconds} -- no redirect --
    with their own TTL; the link serves the bytes as an attachment under
    the original filename (the SVG/HTML-as-XSS defence, Round 4 SEC-01)."""
    content = b"%PDF-1.4\n%storage links test\n"
    company_id, attachment_id, token = await _company_with_attachment(
        client,
        db_session,
        is_published=True,
        is_public=True,
        filename="report.pdf",
        content=content,
    )

    for path, headers, ttl in (
        (
            f"/api/v1/companies/{company_id}/attachments/{attachment_id}/download",
            auth_headers(token),
            settings.storage_presigned_ttl_auth,
        ),
        (
            f"/api/v1/public/companies/{company_id}"
            f"/attachments/{attachment_id}/download",
            {"X-Real-IP": f"192.0.2.{uuid.uuid4().int % 200 + 50}"},
            settings.storage_presigned_ttl_public,
        ),
    ):
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200, resp.text
        assert "location" not in resp.headers
        body = resp.json()
        assert body["ttl_seconds"] == ttl
        url = body["url"]
        assert url
        _assert_sigv4(url, ttl)
        assert _query(url)["response-content-disposition"] == (
            'attachment; filename="report.pdf"'
        )

        async with httpx.AsyncClient() as http:
            served = await http.get(url)
        assert served.status_code == 200
        assert served.content == content
        assert served.headers["content-disposition"] == (
            'attachment; filename="report.pdf"'
        )


@pytest.mark.asyncio
async def test_attachment_that_may_not_be_seen_gets_no_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Unpublished: 404 on both endpoints. Published but not public: the
    authenticated endpoint links it, the public one answers 404. A 404
    carries no link."""
    company_id, hidden_id, token = await _company_with_attachment(
        client,
        db_session,
        is_published=False,
        is_public=True,
        filename="draft.pdf",
        content=b"%PDF-1.4\n%draft\n",
    )
    public_ip = {"X-Real-IP": f"192.0.2.{uuid.uuid4().int % 200 + 50}"}

    resp = await client.get(
        f"/api/v1/companies/{company_id}/attachments/{hidden_id}/download",
        headers=auth_headers(token),
    )
    assert resp.status_code == 404
    assert "url" not in resp.json()
    resp = await client.get(
        f"/api/v1/public/companies/{company_id}/attachments/{hidden_id}/download",
        headers=public_ip,
    )
    assert resp.status_code == 404
    assert "url" not in resp.json()

    resp = await client.post(
        "/api/v1/company/attachments",
        data={
            "metadata": json.dumps(
                {
                    "title": "Private document",
                    "category": "legal/incorporation",
                    "order": 0,
                    "is_published": True,
                    "is_public": False,
                }
            )
        },
        files={"file": ("private.pdf", b"%PDF-1.4\n%private\n", "application/pdf")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    private_id = resp.json()["id"]

    resp = await client.get(
        f"/api/v1/companies/{company_id}/attachments/{private_id}/download",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["url"]
    resp = await client.get(
        f"/api/v1/public/companies/{company_id}/attachments/{private_id}/download",
        headers=public_ip,
    )
    assert resp.status_code == 404
    assert "url" not in resp.json()


# ---------------------------------------------------------------------------
# 4: roadmap covers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roadmap_item_with_a_cover_renders_on_every_surface(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The item WITH a cover -- the case that answered 500 -- renders for
    staff (the upload response), for the company and on the public page,
    each with its own TTL, and the link serves the image. An item without
    a cover renders with cover_url null on the same surfaces."""
    _admin, admin_token = await create_admin_user(client, db_session)
    email = f"cocover_{uuid.uuid4().hex[:12]}@example.com"
    password = "companypass123"
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": email,
            "password": password,
            "name": f"CoverCo {uuid.uuid4().hex[:8]}",
            "description": "Roadmap cover test company",
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
    company_id = resp.json()["id"]
    token = (await login_user(client, email=email, password=password))[
        "session_token"
    ]

    items = {}
    for name in ("with_cover", "without_cover"):
        resp = await client.post(
            "/api/v1/company/roadmap",
            json={"kind": "milestone", "title": f"{name} {uuid.uuid4().hex[:6]}"},
            headers=auth_headers(token),
        )
        assert resp.status_code == 201, resp.text
        items[name] = resp.json()["id"]

    # Staff uploads the cover; the response renders the item with it.
    resp = await client.put(
        f"/api/v1/staff/companies/{company_id}/roadmap/{items['with_cover']}/cover",
        files={"file": ("cover.png", _PNG, "image/png")},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    staff_url = resp.json()["cover_url"]
    assert staff_url
    _assert_sigv4(staff_url, settings.storage_presigned_ttl_auth)
    async with httpx.AsyncClient() as http:
        served = await http.get(staff_url)
    assert served.status_code == 200
    assert served.content == _PNG

    # The company's own screen.
    resp = await client.get("/api/v1/company/roadmap", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    by_id = {item["id"]: item for item in resp.json()}
    _assert_sigv4(
        by_id[items["with_cover"]]["cover_url"],
        settings.storage_presigned_ttl_auth,
    )
    assert by_id[items["without_cover"]]["cover_url"] is None

    # The public page (an active company with a pool).
    resp = await client.post(
        f"/api/v1/staff/companies/{company_id}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    resp = await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get(
        f"/api/v1/public/companies/{company_id}",
        headers={"X-Real-IP": f"192.0.2.{uuid.uuid4().int % 200 + 50}"},
    )
    assert resp.status_code == 200, resp.text
    by_id = {item["id"]: item for item in resp.json()["roadmap"]}
    _assert_sigv4(
        by_id[items["with_cover"]]["cover_url"],
        settings.storage_presigned_ttl_public,
    )
    assert by_id[items["without_cover"]]["cover_url"] is None
