# =============================================================================
# AIVIS.ONE Backend -- GET /api/v1/documents/by-type/{type} Tests
# =============================================================================
#
# Tests cover:
#   1: A document that no role has to sign is not in the list, but
#      by-type returns it (id, version, title, is_signed) to any
#      signed-in user, and it can be signed by that id
#   2: The language is `lang`, else the caller's own, else English; the
#      highest active version wins; archived rows are ignored
#   3: A type with no active row -> 404
#   4: Without a token -> 401
# =============================================================================

import uuid
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document, DocumentStatus
from tests.helpers import auth_headers, register_user


def _document(
    doc_type: str, language: str, version: int, created_by: UUID, **kw
) -> Document:
    return Document(
        type=doc_type,
        version=version,
        language=language,
        title=kw.get("title", f"{doc_type} {language} v{version}"),
        required_for_roles=[],
        content_hash="",
        status=kw.get("status", DocumentStatus.ACTIVE),
        created_by=created_by,
    )


@pytest.mark.asyncio
async def test_a_no_roles_document_is_read_and_signed_by_its_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await register_user(client)
    token = user["session_token"]
    doc_type = f"bytype_{uuid.uuid4().hex[:10]}"
    doc = _document(doc_type, "en", 1, UUID(user["user"]["id"]))
    db_session.add(doc)
    await db_session.commit()

    listed = await client.get("/api/v1/documents", headers=auth_headers(token))
    assert listed.status_code == 200, listed.text
    assert doc_type not in {d["type"] for d in listed.json()}

    resp = await client.get(
        f"/api/v1/documents/by-type/{doc_type}", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(doc.id)
    assert body["version"] == 1
    assert body["title"] == doc.title
    assert body["is_signed"] is False

    signed = await client.post(
        f"/api/v1/documents/{body['id']}/sign", headers=auth_headers(token)
    )
    assert signed.status_code == 201, signed.text

    again = await client.get(
        f"/api/v1/documents/by-type/{doc_type}", headers=auth_headers(token)
    )
    assert again.json()["is_signed"] is True


@pytest.mark.asyncio
async def test_language_version_and_status_are_resolved(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await register_user(client)
    token = user["session_token"]
    uid = UUID(user["user"]["id"])
    doc_type = f"bytype_{uuid.uuid4().hex[:10]}"
    en1 = _document(doc_type, "en", 1, uid)
    en2 = _document(doc_type, "en", 2, uid)
    ru1 = _document(doc_type, "ru", 1, uid)
    old_ru = _document(doc_type, "ru", 9, uid, status=DocumentStatus.ARCHIVED)
    db_session.add_all([en1, en2, ru1, old_ru])
    await db_session.commit()

    ru = await client.get(
        f"/api/v1/documents/by-type/{doc_type}?lang=ru",
        headers=auth_headers(token),
    )
    assert ru.status_code == 200, ru.text
    assert ru.json()["id"] == str(ru1.id)  # archived v9 is ignored

    en = await client.get(
        f"/api/v1/documents/by-type/{doc_type}?lang=en",
        headers=auth_headers(token),
    )
    assert en.json()["id"] == str(en2.id)  # the highest active version

    # A language with no row falls back to English.
    other = await client.get(
        f"/api/v1/documents/by-type/{doc_type}?lang=de",
        headers=auth_headers(token),
    )
    assert other.status_code == 200, other.text
    assert other.json()["id"] == str(en2.id)


@pytest.mark.asyncio
async def test_unknown_type_is_404_and_a_token_is_required(
    client: AsyncClient,
) -> None:
    user = await register_user(client)
    missing = await client.get(
        f"/api/v1/documents/by-type/none_{uuid.uuid4().hex[:10]}",
        headers=auth_headers(user["session_token"]),
    )
    assert missing.status_code == 404, missing.text

    anonymous = await client.get("/api/v1/documents/by-type/anything")
    assert anonymous.status_code == 401
