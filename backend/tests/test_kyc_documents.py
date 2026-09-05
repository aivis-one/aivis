# =============================================================================
# AIVIS.ONE Backend -- KYC Documents, Presign, Permission, Mode (H12)
# =============================================================================
#
# Tests cover:
#   Upload and read back -- PAIRED
#     1: submit stores every required object AND each reads back byte for
#        byte through the staff presign path
#     2: a passport submission carries front + selfie and nothing else
#     3: an id_card submission requires the reverse
#     4: two documents of one application never share an object key
#
#   Audit of the handout -- CONTENT, not the existence of a row
#     5: issuing a link writes actor, target and the object key
#     6: listing the documents writes NOTHING -- opening a card is not
#        reading a passport
#
#   The kyc_approve permission -- PAIRED, both directions
#     7: staff without it are refused the list and the link
#     8: staff with it get both
#     9: a freshly created staff profile does NOT have it (P-46d)
#
#   The verification mode switch
#    10: unset reads manual; set reads back; survives a process restart
#    11: an unknown value is refused by the schema, never reaching the db
#    12: the mode is stamped on the application at submit time
#
#   File validation -- one test per refused case, and every one of them
#   asserts THE MONEY WAS NOT TAKEN
#    13: no files at all
#    14: an empty file
#    15: a file with no extension
#    16: HEIC, refused by its own code and not as "unknown"
#    17: a disallowed type (pdf)
#    18: over the size cap
#    19: a passport carrying a back image
#    20: an id_card missing its back image
#
#   Vocabulary (P-46f)
#    21: both CHECK constraints admit exactly KYCStatus's members
#
# WHY THE PAIRING IN 1, 7/8 AND 6. A test that only asserts "the upload
# was accepted" passes against a service that writes a row and drops the
# bytes; a test that only asserts "staff without the permission are
# refused" passes against an endpoint that refuses everybody. Each of
# those three states an absence AND the matching presence.
#
# REAL MinIO, no moto and no mock -- same stance test_storage.py takes
# and for the same reason: a green run against a substitute is a
# statement about the substitute. CI raises MinIO with both buckets.
#
# Email prefix: "h12_" -- unique to this file.
# =============================================================================

import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.core.config import settings
from app.core.storage import delete_object, list_objects
from app.modules.kyc.constants import (
    KYC_MAX_DOCUMENT_BYTES,
    KYC_VERIFICATION_FEE_CENTS,
    VerificationMode,
)
from app.modules.kyc.models import KYCApplication, KYCDocument, KYCSettings
from app.modules.ledgers.service import get_active_balance
from app.modules.staff.models import StaffProfile
from app.modules.users.models import KYCStatus
from tests.helpers import (
    KYC_FIXTURE_BYTES,
    KYC_SUBMIT_URL,
    auth_headers,
    create_admin_user,
    create_staff_user,
    fund_user,
    kyc_document_files,
    register_user,
    submit_kyc_application,
)

TEST_BUCKET = "aivis-attachments-test"


@pytest.fixture(autouse=True)
async def use_test_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[None, None]:
    """Point storage at the test bucket and wipe it before each test.

    Same fixture, same reasoning as tests/test_storage.py: pre-clean
    rather than post-clean, so a failed test leaves the bucket in a
    state that can be inspected by hand.
    """
    monkeypatch.setattr(settings, "minio_bucket", TEST_BUCKET)
    for key in await list_objects(""):
        await delete_object(key)
    yield


async def _funded_investor(client: AsyncClient) -> tuple[str, UUID]:
    """A registered investor holding exactly one verification fee."""
    data = await register_user(client, verified=False)
    user_id = UUID(data["user"]["id"])
    await fund_user(user_id, KYC_VERIFICATION_FEE_CENTS)
    return data["session_token"], user_id


async def _application_id(session: AsyncSession, user_id: UUID) -> UUID:
    stmt = (
        select(KYCApplication)
        .where(KYCApplication.user_id == user_id)
        .order_by(KYCApplication.created_at.desc())
        .limit(1)
    )
    application = (await session.execute(stmt)).scalar_one()
    return application.id


# ---------------------------------------------------------------------------
# 1: upload and read back -- the pair
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_documents_are_stored_and_read_back_by_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Submit stores the objects AND staff read the same bytes back.

    THE SECOND HALF IS THE POINT. "The upload was accepted" passes
    against a service that writes rows and throws the bytes away; this
    fetches each presigned URL and compares the body with what was sent,
    through the same path and the same credentials staff will use.
    """
    _staff, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _funded_investor(client)

    resp = await submit_kyc_application(client, token)
    assert resp.status_code == 201, resp.text

    application_id = await _application_id(db_session, user_id)

    listing = await client.get(
        f"/api/v1/staff/kyc/{application_id}/documents",
        headers=auth_headers(staff_token),
    )
    assert listing.status_code == 200, listing.text
    documents = listing.json()
    assert {d["kind"] for d in documents} == {"front", "selfie"}

    for document in documents:
        link = await client.post(
            f"/api/v1/staff/kyc/documents/{document['id']}/url",
            headers=auth_headers(staff_token),
        )
        assert link.status_code == 200, link.text
        body = link.json()
        assert body["ttl_seconds"] == 300

        async with httpx.AsyncClient() as raw:
            fetched = await raw.get(body["url"])
        assert fetched.status_code == 200
        assert fetched.content == KYC_FIXTURE_BYTES[document["kind"]]


@pytest.mark.asyncio
async def test_id_card_stores_all_three_faces(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An id_card submission carries front, back and selfie."""
    token, user_id = await _funded_investor(client)

    resp = await submit_kyc_application(
        client, token, document_type="id_card", include_back=True
    )
    assert resp.status_code == 201, resp.text

    application_id = await _application_id(db_session, user_id)
    rows = (
        await db_session.execute(
            select(KYCDocument).where(KYCDocument.application_id == application_id)
        )
    ).scalars().all()
    assert {r.kind for r in rows} == {"front", "back", "selfie"}


@pytest.mark.asyncio
async def test_object_keys_are_distinct_within_one_application(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two documents of one application never name one object.

    The REPEAT axis for the object key. Keys are built from two UUID4s,
    so a collision cannot happen by accident -- which is why a
    regression that dropped the per-document id from the key would go
    unnoticed without this assertion, and would have each upload
    overwrite the last.
    """
    token, user_id = await _funded_investor(client)
    resp = await submit_kyc_application(
        client, token, document_type="driving_licence", include_back=True
    )
    assert resp.status_code == 201, resp.text

    application_id = await _application_id(db_session, user_id)
    rows = (
        await db_session.execute(
            select(KYCDocument).where(KYCDocument.application_id == application_id)
        )
    ).scalars().all()

    keys = [r.storage_key for r in rows]
    assert len(set(keys)) == len(keys) == 3
    for key in keys:
        assert key.startswith(f"kyc/applications/{application_id}/")
        # Nothing the uploader chose may appear in the key: the fixture
        # filenames are "front.jpg" / "back.jpg" / "selfie.jpg".
        assert "front" not in key and "selfie" not in key


# ---------------------------------------------------------------------------
# 5-6: the audit of a handout, by content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issuing_a_link_audits_actor_target_and_key(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The audit row names who looked, at whom, and at which object.

    NOT "a row exists". With documents kept forever, the question asked
    after something happens is "who looked at this person's passport",
    and a row that records the act without the object cannot answer it
    for an application holding three.
    """
    staff_user, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _funded_investor(client)
    assert (await submit_kyc_application(client, token)).status_code == 201

    application_id = await _application_id(db_session, user_id)
    document = (
        await db_session.execute(
            select(KYCDocument).where(KYCDocument.application_id == application_id)
        )
    ).scalars().first()
    assert document is not None

    link = await client.post(
        f"/api/v1/staff/kyc/documents/{document.id}/url",
        headers=auth_headers(staff_token),
    )
    assert link.status_code == 200, link.text

    rows = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.event == "kyc.document_viewed")
            .where(AuditLog.target_id == user_id)
        )
    ).scalars().all()
    assert len(rows) == 1

    row = rows[0]
    assert row.actor_id == staff_user.id
    assert row.actor_type == "staff"
    assert row.target_type == "user"
    assert row.data["storage_key"] == document.storage_key
    assert row.data["document_id"] == str(document.id)
    assert row.data["application_id"] == str(application_id)


@pytest.mark.asyncio
async def test_listing_documents_is_not_a_view(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Listing writes no view row -- opening a card is not reading a passport.

    The counterpart to the test above. If the list endpoint audited,
    every staff member opening a user's detail modal would appear to
    have read their identity documents, and the log answering "who
    looked" would name everybody.
    """
    _staff, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _funded_investor(client)
    assert (await submit_kyc_application(client, token)).status_code == 201
    application_id = await _application_id(db_session, user_id)

    listing = await client.get(
        f"/api/v1/staff/kyc/{application_id}/documents",
        headers=auth_headers(staff_token),
    )
    assert listing.status_code == 200

    rows = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.event == "kyc.document_viewed")
            .where(AuditLog.target_id == user_id)
        )
    ).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# 7-9: the kyc_approve permission, both directions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_without_kyc_approve_cannot_see_documents(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No permission -> refused on both the list and the link.

    Paired with the test below, which proves the endpoints are not
    simply refusing everybody.
    """
    _staff, staff_token = await create_staff_user(client, db_session)
    token, user_id = await _funded_investor(client)
    assert (await submit_kyc_application(client, token)).status_code == 201
    application_id = await _application_id(db_session, user_id)

    listing = await client.get(
        f"/api/v1/staff/kyc/{application_id}/documents",
        headers=auth_headers(staff_token),
    )
    assert listing.status_code == 403, listing.text

    document = (
        await db_session.execute(
            select(KYCDocument).where(KYCDocument.application_id == application_id)
        )
    ).scalars().first()
    assert document is not None

    link = await client.post(
        f"/api/v1/staff/kyc/documents/{document.id}/url",
        headers=auth_headers(staff_token),
    )
    assert link.status_code == 403, link.text


@pytest.mark.asyncio
async def test_staff_with_kyc_approve_gets_documents_and_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The permission granted -> the list and a working link."""
    _staff, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _funded_investor(client)
    assert (await submit_kyc_application(client, token)).status_code == 201
    application_id = await _application_id(db_session, user_id)

    listing = await client.get(
        f"/api/v1/staff/kyc/{application_id}/documents",
        headers=auth_headers(staff_token),
    )
    assert listing.status_code == 200, listing.text
    assert len(listing.json()) == 2

    link = await client.post(
        f"/api/v1/staff/kyc/documents/{listing.json()[0]['id']}/url",
        headers=auth_headers(staff_token),
    )
    assert link.status_code == 200, link.text
    assert link.json()["url"]


@pytest.mark.asyncio
async def test_new_staff_profile_does_not_carry_kyc_approve(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """P-46d: hiring somebody no longer hands them every passport.

    Asserts the stored snapshot, not the endpoint, because the snapshot
    is what create_staff() writes and what an admin later edits. The
    endpoint pair above covers the consequence.
    """
    staff_user, _token = await create_staff_user(client, db_session)
    profile = (
        await db_session.execute(
            select(StaffProfile).where(StaffProfile.user_id == staff_user.id)
        )
    ).scalar_one()

    assert profile.permissions["kyc_approve"] is False


# ---------------------------------------------------------------------------
# 10-12: the verification mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verification_mode_defaults_reads_back_and_survives_restart(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Unset -> manual; set -> reads back; and it is in Postgres.

    THE RESTART HALF IS THE ROW, not a second process. What the
    requirement rules out is a value held in memory, and the way to
    show it is not held in memory is to find it in the table that
    outlives the process. A fresh interpreter would prove the same
    thing more slowly and could not run inside this suite.
    """
    _staff, staff_token = await create_admin_user(client, db_session)

    # No row yet on a clean box: the default answers.
    await db_session.execute(text("DELETE FROM kyc_settings"))
    await db_session.commit()

    initial = await client.get(
        "/api/v1/staff/kyc/verification-mode",
        headers=auth_headers(staff_token),
    )
    assert initial.status_code == 200, initial.text
    assert initial.json()["mode"] == VerificationMode.MANUAL

    changed = await client.put(
        "/api/v1/staff/kyc/verification-mode",
        headers=auth_headers(staff_token),
        json={"mode": "automatic"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["mode"] == "automatic"

    again = await client.get(
        "/api/v1/staff/kyc/verification-mode",
        headers=auth_headers(staff_token),
    )
    assert again.json()["mode"] == "automatic"

    row = (await db_session.execute(select(KYCSettings))).scalar_one()
    assert row.verification_mode == "automatic"


@pytest.mark.asyncio
async def test_verification_mode_rejects_an_unknown_value(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A word outside the vocabulary never reaches the database.

    The SHORTAGE axis for the setting value. Refused by the request
    model, so the service is never called and the CHECK constraint
    behind it is never exercised from this direction -- which is the
    intended layering, not a gap: the constraint is there for the hand
    that edits the table directly.
    """
    _staff, staff_token = await create_admin_user(client, db_session)

    resp = await client.put(
        "/api/v1/staff/kyc/verification-mode",
        headers=auth_headers(staff_token),
        json={"mode": "MANUAL"},
    )
    assert resp.status_code == 422, resp.text

    rows = (
        await db_session.execute(
            select(KYCSettings).where(KYCSettings.verification_mode == "MANUAL")
        )
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_mode_is_stamped_on_the_application_at_submit_time(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The row records the mode in force when it was paid for.

    Switching the platform afterwards must not change how an
    already-open session is handled -- otherwise one click would empty
    the queue nobody emptied.
    """
    _staff, staff_token = await create_admin_user(client, db_session)

    assert (
        await client.put(
            "/api/v1/staff/kyc/verification-mode",
            headers=auth_headers(staff_token),
            json={"mode": "automatic"},
        )
    ).status_code == 200

    token, user_id = await _funded_investor(client)
    assert (await submit_kyc_application(client, token)).status_code == 201
    application_id = await _application_id(db_session, user_id)

    application = (
        await db_session.execute(
            select(KYCApplication).where(KYCApplication.id == application_id)
        )
    ).scalar_one()
    assert application.decision_mode == "automatic"
    assert application.document_type == "passport"

    # Move the switch back; the row does not move with it.
    assert (
        await client.put(
            "/api/v1/staff/kyc/verification-mode",
            headers=auth_headers(staff_token),
            json={"mode": "manual"},
        )
    ).status_code == 200

    await db_session.refresh(application)
    assert application.decision_mode == "automatic"


# ---------------------------------------------------------------------------
# 13-20: validation -- one refused case per test, and the money survives
# ---------------------------------------------------------------------------


async def _assert_nothing_charged(
    session: AsyncSession, user_id: UUID
) -> None:
    """The fee is intact and no application row exists.

    Every refusal test ends here. A validation that refuses the request
    but has already taken the money is the failure this ordering exists
    to prevent, and asserting only the status code would not see it.
    """
    balance = await get_active_balance(session, user_id)
    assert balance["frozen"] + balance["confirmed"] == KYC_VERIFICATION_FEE_CENTS

    rows = (
        await session.execute(
            select(KYCApplication).where(KYCApplication.user_id == user_id)
        )
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_submit_without_any_files_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The empty body the endpoint used to accept."""
    token, user_id = await _funded_investor(client)

    resp = await client.post(
        KYC_SUBMIT_URL,
        headers=auth_headers(token),
        data={"document_type": "passport"},
    )
    assert resp.status_code == 422, resp.text
    await _assert_nothing_charged(db_session, user_id)


@pytest.mark.asyncio
async def test_empty_file_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zero bytes -- a picker opened and cancelled, not a document."""
    token, user_id = await _funded_investor(client)

    files: dict[str, Any] = kyc_document_files()
    files["front_image"] = ("front.jpg", b"", "image/jpeg")

    resp = await client.post(
        KYC_SUBMIT_URL,
        headers=auth_headers(token),
        data={"document_type": "passport"},
        files=files,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "kyc_document_empty"
    await _assert_nothing_charged(db_session, user_id)


@pytest.mark.asyncio
async def test_file_without_extension_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No extension means no way to resolve a type we trust."""
    token, user_id = await _funded_investor(client)

    files: dict[str, Any] = kyc_document_files()
    files["front_image"] = ("passport", b"abc", "image/jpeg")

    resp = await client.post(
        KYC_SUBMIT_URL,
        headers=auth_headers(token),
        data={"document_type": "passport"},
        files=files,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "kyc_document_no_extension"
    await _assert_nothing_charged(db_session, user_id)


@pytest.mark.asyncio
async def test_heic_is_refused_by_its_own_code(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """HEIC gets its own refusal, not "unsupported file type".

    An iPhone owner picking a photo out of the Files app sends one
    routinely, and a generic refusal tells them nothing they can act
    on. The distinct code is what lets the screen say "re-save as
    JPEG".
    """
    token, user_id = await _funded_investor(client)

    files: dict[str, Any] = kyc_document_files()
    files["front_image"] = ("front.HEIC", b"abc", "image/heic")

    resp = await client.post(
        KYC_SUBMIT_URL,
        headers=auth_headers(token),
        data={"document_type": "passport"},
        files=files,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "kyc_document_heic"
    await _assert_nothing_charged(db_session, user_id)


@pytest.mark.asyncio
async def test_disallowed_type_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PDF is on the company-attachment whitelist and not on this one."""
    token, user_id = await _funded_investor(client)

    files: dict[str, Any] = kyc_document_files()
    files["front_image"] = ("front.pdf", b"%PDF-1.4", "application/pdf")

    resp = await client.post(
        KYC_SUBMIT_URL,
        headers=auth_headers(token),
        data={"document_type": "passport"},
        files=files,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "kyc_document_type_not_allowed"
    await _assert_nothing_charged(db_session, user_id)


@pytest.mark.asyncio
async def test_oversized_file_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """One byte over the cap."""
    token, user_id = await _funded_investor(client)

    files: dict[str, Any] = kyc_document_files()
    files["front_image"] = (
        "front.jpg",
        b"x" * (KYC_MAX_DOCUMENT_BYTES + 1),
        "image/jpeg",
    )

    resp = await client.post(
        KYC_SUBMIT_URL,
        headers=auth_headers(token),
        data={"document_type": "passport"},
        files=files,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "kyc_document_too_large"
    await _assert_nothing_charged(db_session, user_id)


@pytest.mark.asyncio
async def test_passport_with_a_back_image_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A passport's identity page is one page.

    The set check, not the file check: every part here is individually
    acceptable and the combination is not.
    """
    token, user_id = await _funded_investor(client)

    resp = await client.post(
        KYC_SUBMIT_URL,
        headers=auth_headers(token),
        data={"document_type": "passport"},
        files=kyc_document_files(include_back=True),
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "kyc_documents_incomplete"
    await _assert_nothing_charged(db_session, user_id)


@pytest.mark.asyncio
async def test_id_card_without_a_back_image_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The other direction: half a document is not a document."""
    token, user_id = await _funded_investor(client)

    resp = await client.post(
        KYC_SUBMIT_URL,
        headers=auth_headers(token),
        data={"document_type": "id_card"},
        files=kyc_document_files(include_back=False),
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "kyc_documents_incomplete"
    await _assert_nothing_charged(db_session, user_id)


# ---------------------------------------------------------------------------
# 21: one vocabulary, two constraints (P-46f)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_kyc_status_constraints_match_the_enum(
    db_session: AsyncSession,
) -> None:
    """users.kyc_status and kyc_applications.status admit exactly KYCStatus.

    THIS TEST IS THE MECHANISM, not a convention. The two columns carry
    one vocabulary -- one is a denormalised cache of the other -- and
    until H12 each had its own Python enum and its own CHECK, kept level
    by whoever remembered to edit both. The enums are now one; this
    reads both constraints out of the catalogue and asserts each admits
    the same member set, so a widening that touches one column and
    forgets the other goes red on the day it lands rather than on the
    day a value is written.

    A migration cannot import the enum (a frozen file that imports live
    code starts lying the moment that code moves), so the comparison
    has to live somewhere that can see both sides. That is here.
    """
    expected = {member.value for member in KYCStatus}

    stmt = text(
        """
        SELECT conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conname IN (
            'ck_users_kyc_status',
            'ck_kyc_applications_status'
        )
        """
    )
    rows = (await db_session.execute(stmt)).all()
    assert len(rows) == 2, f"expected both constraints, found {rows}"

    for name, definition in rows:
        found = set(re.findall(r"'([a-z_]+)'", definition))
        assert found == expected, (
            f"{name} admits {sorted(found)}, KYCStatus is {sorted(expected)}"
        )


# ---------------------------------------------------------------------------
# A missing object is a 404, not a signed link to nothing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_object_is_not_presigned(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The SHORTAGE axis for the object key: row present, object gone.

    Presigning is a local computation and succeeds against a key that
    does not exist, handing staff a link that fails at MinIO -- which
    reads as "the link is broken" rather than "the document is gone",
    and writes an audit row claiming a view that could not happen.
    """
    _staff, staff_token = await create_admin_user(client, db_session)
    token, user_id = await _funded_investor(client)
    assert (await submit_kyc_application(client, token)).status_code == 201

    application_id = await _application_id(db_session, user_id)
    document = (
        await db_session.execute(
            select(KYCDocument).where(KYCDocument.application_id == application_id)
        )
    ).scalars().first()
    assert document is not None

    await delete_object(document.storage_key)

    link = await client.post(
        f"/api/v1/staff/kyc/documents/{document.id}/url",
        headers=auth_headers(staff_token),
    )
    assert link.status_code == 404, link.text

    rows = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.event == "kyc.document_viewed")
            .where(AuditLog.target_id == user_id)
        )
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_unknown_document_id_is_a_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An id that names nothing, rather than an object that is missing."""
    _staff, staff_token = await create_admin_user(client, db_session)

    link = await client.post(
        f"/api/v1/staff/kyc/documents/{uuid.uuid4()}/url",
        headers=auth_headers(staff_token),
    )
    assert link.status_code == 404, link.text


@pytest.mark.asyncio
async def test_application_without_documents_lists_empty_not_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A person approved by hand has an application and no documents.

    An empty list is the honest answer; 404 would say the application
    does not exist, which is false and sends staff looking for a bug.
    """
    staff_user, staff_token = await create_admin_user(client, db_session)
    data = await register_user(client, verified=False)
    user_id = UUID(data["user"]["id"])

    approved = await client.post(
        f"/api/v1/staff/kyc/users/{user_id}/approve",
        headers=auth_headers(staff_token),
        json={"reason": "Known to us from the old platform."},
    )
    assert approved.status_code == 204, approved.text

    application_id = await _application_id(db_session, user_id)
    listing = await client.get(
        f"/api/v1/staff/kyc/{application_id}/documents",
        headers=auth_headers(staff_token),
    )
    assert listing.status_code == 200, listing.text
    assert listing.json() == []
    assert staff_user is not None
