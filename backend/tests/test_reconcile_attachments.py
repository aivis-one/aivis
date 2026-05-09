# =============================================================================
# CBSHOME Backend -- Reconcile Attachments Tests
#                     (Refactor 2 iter 2.2, batch G2)
# =============================================================================
#
# Tests the script's two-direction reconciliation by calling the public
# helpers (reconcile_orphans / reconcile_broken) directly with a test
# AsyncSession. Spinning up the CLI as a subprocess buys nothing here --
# argparse plumbing is trivial; the interesting logic is in the async
# helpers.
#
# Coverage:
#   - orphans: creates a new row when no DB match.
#   - orphans: replaces existing row matched on (title, category, language).
#   - orphans: skips main file with no sidecar (no row created, file
#     stays in inbox so a human can investigate).
#   - broken:  soft-deletes rows whose MinIO object is gone.
#   - dry-run: orphans path makes zero DB / MinIO writes.
#
# Email prefix: "attr_" -- distinct from att_ / attp_ / atts_ used by
# the other attachment test files.
# =============================================================================

import json
from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import (
    delete_object,
    list_objects,
    object_exists,
    upload_object,
)
from app.modules.companies.models import CompanyAttachment
from app.modules.companies.schemas import AttachmentInboxMetadata
from app.modules.companies.service import create_attachment
from app.modules.users.models import User
from scripts.reconcile_attachments import (
    INBOX_PREFIX_TEMPLATE,
    SIDECAR_SUFFIX,
    reconcile_broken,
    reconcile_orphans,
)
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
)

EMAIL_PREFIX = "attr_"
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
    """Clean test users (and their dependent attachments / companies / etc.)."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _admin_and_company(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[User, UUID]:
    """Create admin + one company; return the ORM staff User and company_id."""
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
            "name": "Reconcile Test Co",
            "price_per_unit_cents": 10000,
            "distribution_config": VALID_DIST_CONFIG,
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    company_id = UUID(resp.json()["id"])
    return staff_user, company_id


async def _seed_inbox(
    company_id: UUID,
    *,
    filename: str,
    file_bytes: bytes,
    content_type: str,
    metadata: dict | None,
) -> tuple[str, str | None]:
    """Place a main file and (optionally) its sidecar into the company
    inbox prefix. Returns (main_key, sidecar_key|None)."""
    prefix = INBOX_PREFIX_TEMPLATE.format(company_id=company_id)
    main_key = f"{prefix}{filename}"
    await upload_object(main_key, file_bytes, content_type)

    sidecar_key: str | None = None
    if metadata is not None:
        sidecar_key = main_key + SIDECAR_SUFFIX
        await upload_object(
            sidecar_key,
            json.dumps(metadata).encode("utf-8"),
            "application/json",
        )

    return main_key, sidecar_key


async def _create_attachment_direct(
    db_session: AsyncSession,
    company_id: UUID,
    staff_user: User,
    *,
    title: str,
    category: str = "legal/incorporation",
    language: str | None = "en",
    file_bytes: bytes = b"existing payload",
    original_filename: str = "old.pdf",
    content_type: str = "application/pdf",
    is_published: bool = True,
    is_public: bool = False,
) -> CompanyAttachment:
    """Pre-seed an attachment via the service (used by the replace test)."""
    metadata = AttachmentInboxMetadata(
        title=title,
        category=category,
        language=language,
        is_published=is_published,
        is_public=is_public,
    )
    attachment = await create_attachment(
        session=db_session,
        company_id=company_id,
        staff=staff_user,
        file_bytes=file_bytes,
        original_filename=original_filename,
        content_type=content_type,
        metadata=metadata,
    )
    await db_session.commit()
    return attachment


# ---------------------------------------------------------------------------
# Test 1: orphans -> creates a new attachment when there's no DB match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orphans_creates_new_attachment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Inbox file + sidecar with no matching row -> CREATE + inbox cleaned."""
    _, company_id = await _admin_and_company(client, db_session)

    payload = b"freshly added pdf bytes"
    metadata = {
        "title": "Investor Brief",
        "description": "Q3 update",
        "category": "marketing/presentations",
        "language": "en",
        "order": 0,
        "is_published": True,
        "is_public": True,
    }
    main_key, sidecar_key = await _seed_inbox(
        company_id,
        filename="brief.pdf",
        file_bytes=payload,
        content_type="application/pdf",
        metadata=metadata,
    )

    stats = await reconcile_orphans(db_session, company_id)

    assert stats.created == 1
    assert stats.replaced == 0
    assert stats.skipped == 0

    # Inbox must be empty for this main+sidecar pair.
    assert await object_exists(main_key) is False
    assert sidecar_key is not None
    assert await object_exists(sidecar_key) is False

    # Row exists with the parsed metadata.
    rows = (
        await db_session.execute(
            select(CompanyAttachment).where(
                CompanyAttachment.company_id == company_id
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.title == "Investor Brief"
    assert row.category == "marketing/presentations"
    assert row.language == "en"
    assert row.file_size_bytes == len(payload)
    assert row.is_published is True
    assert row.is_public is True
    # Bytes are parked under the canonical attachments path.
    assert await object_exists(row.storage_key) is True


# ---------------------------------------------------------------------------
# Test 2: orphans -> replaces existing row matched on (title, category, language)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orphans_replaces_existing_match(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Inbox file matching an existing (title, category, language) row -> REPLACE."""
    staff_user, company_id = await _admin_and_company(client, db_session)

    existing = await _create_attachment_direct(
        db_session,
        company_id,
        staff_user,
        title="Investor Brief",
        category="marketing/presentations",
        language="en",
        file_bytes=b"old",
        original_filename="brief.pdf",
    )
    old_storage_key = existing.storage_key
    old_id = existing.id

    new_payload = b"shiny new revision"
    metadata = {
        "title": "Investor Brief",
        "category": "marketing/presentations",
        "language": "en",
    }
    main_key, _ = await _seed_inbox(
        company_id,
        filename="brief_v2.pdf",
        file_bytes=new_payload,
        content_type="application/pdf",
        metadata=metadata,
    )

    stats = await reconcile_orphans(db_session, company_id)

    assert stats.created == 0
    assert stats.replaced == 1

    # Inbox cleaned.
    assert await object_exists(main_key) is False

    # Same row, same id -- but bytes / storage_key / filename refreshed.
    await db_session.refresh(existing)
    assert existing.id == old_id
    assert existing.file_size_bytes == len(new_payload)
    assert existing.original_filename == "brief_v2.pdf"
    assert existing.storage_key != old_storage_key
    # Old object dropped, new object live.
    assert await object_exists(old_storage_key) is False
    assert await object_exists(existing.storage_key) is True


# ---------------------------------------------------------------------------
# Test 3: orphans -> skips main file with no sidecar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orphans_skips_when_sidecar_missing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Main file alone (no cbsmeta.json) is left in inbox; nothing inserted."""
    _, company_id = await _admin_and_company(client, db_session)

    main_key, _ = await _seed_inbox(
        company_id,
        filename="lonely.pdf",
        file_bytes=b"nobody parsed me",
        content_type="application/pdf",
        metadata=None,
    )

    stats = await reconcile_orphans(db_session, company_id)

    assert stats.created == 0
    assert stats.replaced == 0
    assert stats.skipped == 1
    assert any("missing sidecar" in r for r in stats.skipped_reasons)

    # File stays so a human can fix it (add the sidecar) and re-run.
    assert await object_exists(main_key) is True

    # No DB row.
    rows = (
        await db_session.execute(
            select(CompanyAttachment).where(
                CompanyAttachment.company_id == company_id
            )
        )
    ).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# Test 4: broken -> soft-deletes rows whose MinIO object is gone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broken_soft_deletes_missing_object(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Remove the object behind a row, then run broken -> is_deleted=True."""
    staff_user, company_id = await _admin_and_company(client, db_session)

    attachment = await _create_attachment_direct(
        db_session,
        company_id,
        staff_user,
        title="Will Vanish",
    )

    # Sanity check: object is there.
    assert await object_exists(attachment.storage_key) is True

    # Simulate an out-of-band MinIO delete (admin scrubbed it).
    await delete_object(attachment.storage_key)

    stats = await reconcile_broken(db_session, company_id)

    assert stats.inspected == 1
    assert stats.soft_deleted == 1

    await db_session.refresh(attachment)
    assert attachment.is_deleted is True


# ---------------------------------------------------------------------------
# Test 5: dry-run -> no DB or MinIO writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_makes_no_changes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """--dry-run reports the action it would have taken but writes nothing."""
    _, company_id = await _admin_and_company(client, db_session)

    payload = b"would-be created"
    metadata = {
        "title": "Dry Run Doc",
        "category": "legal/incorporation",
        "language": "en",
    }
    main_key, sidecar_key = await _seed_inbox(
        company_id,
        filename="dryrun.pdf",
        file_bytes=payload,
        content_type="application/pdf",
        metadata=metadata,
    )

    stats = await reconcile_orphans(db_session, company_id, dry_run=True)

    # Stats still reflect the would-be action -- callers can show the plan.
    assert stats.created == 1

    # Inbox files are still there (not deleted).
    assert await object_exists(main_key) is True
    assert sidecar_key is not None
    assert await object_exists(sidecar_key) is True

    # No DB row created.
    rows = (
        await db_session.execute(
            select(CompanyAttachment).where(
                CompanyAttachment.company_id == company_id
            )
        )
    ).scalars().all()
    assert rows == []
