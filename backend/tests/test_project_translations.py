# =============================================================================
# AIVIS.ONE Backend -- project data in the reader's language (H38 P-132)
# =============================================================================
#
# A project's texts keep English in their own columns (the base and the
# fallback) and every other language in a `translations` JSONB beside them;
# its pictures may have a variant per language beside the common file
# (`media_variants`). A reader's language is the first tag of
# Accept-Language; a reader is answered in it, else in English, in the
# SAME fields, with `Vary: Accept-Language`. Editing screens also get the
# English base, the stored translations and every picture per language.
#
# What is pinned here:
#   1. the schema: translations on four tables, media_variants on three,
#      NOT NULL with an empty default;
#   2. a translation is saved and served; a reader without one gets English;
#      a language that is no interface language (de) needs no migration;
#   3. the written map: refused keys and fields, blanks dropped, PATCH
#      replaces the map whole, omitted keeps it, {} clears it;
#   4. the reader's language parsed from Accept-Language;
#   5. every surface: storefront list and detail, product, roadmap, news,
#      staff and cabinet editing answers (base + translations), Vary;
#   6. search by a name in any language;
#   7. picture variants for company, product and roadmap covers: served by
#      language, falling back to the common file; en refused as a variant;
#   8. documents: names in the template's language, the legal name English;
#   9. the seed: variant folders and text languages refused before any write.
#
# Axes:
#   REPEAT    -- the same field in two languages; a variant uploaded twice;
#                two readers of one URL (Vary)
#   EMPTINESS -- no translations at all; a blank translation; {} clearing
#                the map; a variant with no common file under it
#   SHORTAGE  -- a reader whose language has no translation (fr); a variant
#                for one slot only, the others falling back; `en` as a key
# =============================================================================

import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import scripts.seed as seed
from app.core.config import settings as seed_settings
from app.core.i18n import normalize_translations, parse_accept_language
from app.modules.companies.models import CompanyProfile
from app.modules.purchases import ownership_certificate_service
from app.modules.purchases.agreement_service import (
    load_agreement_data,
    render_agreement_html,
)
from app.modules.purchases.ownership_certificate_service import (
    load_ownership_data,
    render_ownership_html,
)
from tests.helpers import auth_headers, create_admin_user
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

_RU = {"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}
_EN = {"Accept-Language": "en-US,en;q=0.9"}
_FR = {"Accept-Language": "fr"}


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _project(
    client: AsyncClient,
    admin_token: str,
    *,
    translations: dict | None = None,
    name: str | None = None,
) -> dict:
    """An ACTIVE project with a pool (so products can be made), as staff sees it."""
    body: dict = {
        "email": f"tr_{uuid.uuid4().hex[:12]}@example.com",
        "password": "companypass123",
        "name": name or f"Sunrise Farm {_tag()}",
        "description": "Organic apples from the north",
        "price_per_unit_cents": 10_000,
        "distribution_config": {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]},
        "total_supply": 1_000_000,
        "shares_per_option": 1,
    }
    if translations is not None:
        body["translations"] = translations
    resp = await client.post(
        "/api/v1/staff/companies", json=body, headers=auth_headers(admin_token)
    )
    assert resp.status_code == 201, resp.text
    company = resp.json()
    resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _staff_view(client: AsyncClient, admin_token: str, company_id: str, lang: dict) -> dict:
    resp = await client.get(
        f"/api/v1/staff/companies/{company_id}", headers={**auth_headers(admin_token), **lang}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _public(client: AsyncClient, company_id: str, lang: dict | None = None):
    return await client.get(f"/api/v1/public/companies/{company_id}", headers=lang or {})


# ---------------------------------------------------------------------------
# 1: the schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_translation_and_variant_columns_exist_not_null_and_empty_by_default(
    db_session: AsyncSession,
) -> None:
    """Paired: each column is there AND is NOT NULL with '{}' -- a nullable
    column would make every reader branch on None."""
    rows = (
        await db_session.execute(
            text(
                "SELECT table_name, column_name, is_nullable, column_default, data_type "
                "FROM information_schema.columns "
                "WHERE column_name IN ('translations', 'media_variants')"
            )
        )
    ).all()
    found = {(r[0], r[1]): r for r in rows}
    expected = {
        ("company_profiles", "translations"),
        ("products", "translations"),
        ("company_roadmap_items", "translations"),
        ("posts", "translations"),
        ("company_profiles", "media_variants"),
        ("products", "media_variants"),
        ("company_roadmap_items", "media_variants"),
    }
    assert expected <= set(found)
    for key in expected:
        _, _, nullable, default, data_type = found[key]
        assert nullable == "NO", key
        assert data_type == "jsonb", key
        assert default is not None and "'{}'" in default, key
    # Posts have no pictures of ours (cover_url is a link), so no variants.
    assert ("posts", "media_variants") not in found


# ---------------------------------------------------------------------------
# 2-5: saved, served, refused
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_translation_is_served_to_its_reader_and_english_to_the_rest(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """REPEAT: one project read by en, ru, fr and no header. SHORTAGE: fr has
    no translation -> English. The answer varies on Accept-Language."""
    _, admin_token = await create_admin_user(client, db_session)
    name = f"Sunrise Farm {_tag()}"
    company = await _project(
        client,
        admin_token,
        name=name,
        translations={"ru": {"name": f"Ферма Рассвет {name[-8:]}", "description": "Яблоки"}},
    )
    ru_name = f"Ферма Рассвет {name[-8:]}"

    ru = await _public(client, company["id"], _RU)
    en = await _public(client, company["id"], _EN)
    fr = await _public(client, company["id"], _FR)
    bare = await _public(client, company["id"])
    for resp in (ru, en, fr, bare):
        assert resp.status_code == 200, resp.text
        assert "accept-language" in resp.headers.get("vary", "").lower()
    assert ru.json()["name"] == ru_name
    assert ru.json()["description"] == "Яблоки"
    for resp in (en, fr, bare):
        assert resp.json()["name"] == name
        assert resp.json()["description"] == "Organic apples from the north"

    # The storefront list too, in the same fields.
    listing = await client.get(
        "/api/v1/public/companies", params={"search": name[-8:]}, headers=_RU
    )
    assert listing.status_code == 200, listing.text
    assert [c["name"] for c in listing.json()["items"]] == [ru_name]
    assert "accept-language" in listing.headers.get("vary", "").lower()


@pytest.mark.asyncio
async def test_the_editing_answer_carries_the_base_and_the_stored_map(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff reads the project in Russian: the displayed name is Russian,
    `base` is English, `translations` is the map exactly as stored -- no
    "en" key in it."""
    _, admin_token = await create_admin_user(client, db_session)
    company = await _project(
        client, admin_token, translations={"ru": {"name": "Ферма"}}
    )
    body = await _staff_view(client, admin_token, company["id"], _RU)
    assert body["name"] == "Ферма"
    assert body["base"] == {"name": company["base"]["name"], "description": "Organic apples from the north"}
    assert body["translations"] == {"ru": {"name": "Ферма"}}
    assert "en" not in body["translations"]
    # The description has no Russian -> the English one, in the same field.
    assert body["description"] == "Organic apples from the north"


@pytest.mark.asyncio
async def test_a_new_language_needs_no_migration(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """German is no interface language; it is a key like any other."""
    _, admin_token = await create_admin_user(client, db_session)
    company = await _project(
        client, admin_token, translations={"de": {"name": "Sonnenaufgang Hof"}}
    )
    de = await _public(client, company["id"], {"Accept-Language": "de-DE"})
    assert de.json()["name"] == "Sonnenaufgang Hof"
    ru = await _public(client, company["id"], _RU)
    assert ru.json()["name"] == company["base"]["name"]


@pytest.mark.parametrize(
    "translations",
    [
        {"en": {"name": "English twice"}},
        {"EN": {"name": "x"}},
        {"rus": {"name": "x"}},
        {"ru-RU": {"name": "x"}},
        {"ru": {"title": "a roadmap field on a company"}},
        {"ru": {"name": "x" * 501}},
        {"ru": {"name": 5}},
        {"ru": "not an object"},
    ],
)
@pytest.mark.asyncio
async def test_a_bad_translations_map_is_refused_with_422(
    client: AsyncClient, db_session: AsyncSession, translations: dict
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    company = await _project(client, admin_token)
    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}",
        json={"translations": translations},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_patch_replaces_the_map_whole_omitted_keeps_it_and_empty_clears_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    company = await _project(
        client,
        admin_token,
        translations={"ru": {"name": "Ферма", "description": "Яблоки"}, "de": {"name": "Hof"}},
    )
    url = f"/api/v1/staff/companies/{company['id']}"
    headers = auth_headers(admin_token)

    # Omitted: kept.
    resp = await client.patch(url, json={"description": "New English"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["translations"] == {
        "ru": {"name": "Ферма", "description": "Яблоки"},
        "de": {"name": "Hof"},
    }
    # Explicit null: kept too (the column is NOT NULL; null is "not sent").
    resp = await client.patch(url, json={"translations": None}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["translations"]["de"] == {"name": "Hof"}

    # Sent: replaces the whole map -- de is gone; a blank field is dropped,
    # a language left with nothing is dropped.
    resp = await client.patch(
        url,
        json={"translations": {"ru": {"name": "Ферма 2", "description": "  "}, "uk": {"name": ""}}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["translations"] == {"ru": {"name": "Ферма 2"}}
    ru = await _public(client, company["id"], _RU)
    # The blank Russian description is "no translation": English shows.
    assert ru.json()["description"] == "New English"

    # {}: cleared.
    resp = await client.patch(url, json={"translations": {}}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["translations"] == {}
    db_session.expire_all()
    row = await db_session.get(CompanyProfile, UUID(company["id"]))
    assert row.translations == {}


def test_normalize_translations_keeps_text_and_drops_blanks() -> None:
    assert normalize_translations(
        "posts", {"ru": {"title": "Заголовок", "body": None}, "de": {"title": " "}}
    ) == {"ru": {"title": "Заголовок"}}
    assert normalize_translations("posts", {}) == {}
    with pytest.raises(ValueError):
        normalize_translations("posts", {"ru": {"name": "a company field on a post"}})


@pytest.mark.parametrize(
    ("header", "language"),
    [
        (None, "en"),
        ("", "en"),
        ("ru", "ru"),
        ("ru-RU,ru;q=0.9,en;q=0.8", "ru"),
        ("RU-ru", "ru"),
        ("en;q=0.5,de;q=0.9", "de"),
        ("de;q=0.9,fr;q=0.9", "de"),
        ("*", "en"),
        ("zh-Hant-TW", "zh"),
        ("123,,;", "en"),
        ("x-klingon", "en"),
        ("ru;q=abc,de", "de"),
    ],
)
def test_the_readers_language_from_accept_language(header: str | None, language: str) -> None:
    assert parse_accept_language(header) == language


# ---------------------------------------------------------------------------
# 5: products, roadmap, news
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_product_and_its_projects_name_are_in_the_readers_language(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    company = await _project(client, admin_token, translations={"ru": {"name": "Ферма"}})
    resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company["id"],
            "name": "Starter package",
            "description": "Ten parts",
            "package_size": 10,
            "translations": {"ru": {"name": "Стартовый пакет"}},
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    product = resp.json()
    assert product["base"] == {"name": "Starter package", "description": "Ten parts"}
    assert product["translations"] == {"ru": {"name": "Стартовый пакет"}}
    resp = await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text

    ru = await client.get(f"/api/v1/public/products/{product['id']}", headers=_RU)
    en = await client.get(f"/api/v1/public/products/{product['id']}", headers=_EN)
    assert ru.status_code == en.status_code == 200, (ru.text, en.text)
    assert (ru.json()["name"], ru.json()["company_name"]) == ("Стартовый пакет", "Ферма")
    # The description has no Russian -> English.
    assert ru.json()["description"] == "Ten parts"
    assert (en.json()["name"], en.json()["company_name"]) == (
        "Starter package",
        company["base"]["name"],
    )
    assert "accept-language" in ru.headers.get("vary", "").lower()

    # The PATCH: replaces the map, the English name stays.
    resp = await client.patch(
        f"/api/v1/staff/products/{product['id']}",
        json={"translations": {"ru": {"description": "Десять частей"}}},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    ru = await client.get(f"/api/v1/public/products/{product['id']}", headers=_RU)
    assert ru.json()["name"] == "Starter package"
    assert ru.json()["description"] == "Десять частей"


@pytest.mark.asyncio
async def test_a_roadmap_item_is_in_the_readers_language_on_the_storefront(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    company = await _project(client, admin_token)
    resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/roadmap",
        json={
            "kind": "milestone",
            "title": "Platform launch",
            "translations": {"ru": {"title": "Запуск платформы"}},
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    item = resp.json()
    assert item["base"] == {"title": "Platform launch", "description": None}
    assert item["translations"] == {"ru": {"title": "Запуск платформы"}}

    ru = await _public(client, company["id"], _RU)
    en = await _public(client, company["id"], _EN)
    assert [i["title"] for i in ru.json()["roadmap"]] == ["Запуск платформы"]
    assert [i["title"] for i in en.json()["roadmap"]] == ["Platform launch"]
    # The storefront gets no editing fields.
    assert ru.json()["roadmap"][0]["base"] is None
    assert ru.json()["roadmap"][0]["translations"] is None

    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}/roadmap/{item['id']}",
        json={"translations": {}},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["translations"] == {}
    ru = await _public(client, company["id"], _RU)
    assert [i["title"] for i in ru.json()["roadmap"]] == ["Platform launch"]


@pytest.mark.asyncio
async def test_a_post_is_in_the_readers_language_in_the_feed_and_the_detail(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    title = f"Harvest news {_tag()}"
    resp = await client.post(
        "/api/v1/staff/posts",
        json={
            "owner_type": "platform",
            "title": title,
            "body": "The harvest is in.",
            "is_published": True,
            "translations": {"ru": {"title": "Новости урожая", "body": "Урожай собран."}},
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    post = resp.json()
    # The staff editor gets the base and the map.
    assert post["base"] == {"title": title, "body": "The harvest is in."}
    assert post["translations"] == {"ru": {"title": "Новости урожая", "body": "Урожай собран."}}

    ru = await client.get(f"/api/v1/posts/{post['id']}", headers=_RU)
    en = await client.get(f"/api/v1/posts/{post['id']}", headers=_EN)
    assert (ru.json()["title"], ru.json()["body"]) == ("Новости урожая", "Урожай собран.")
    assert (en.json()["title"], en.json()["body"]) == (title, "The harvest is in.")
    # The reader's feed carries no editing fields.
    assert ru.json()["base"] is None and ru.json()["translations"] is None
    assert "accept-language" in ru.headers.get("vary", "").lower()

    feed = await client.get("/api/v1/posts", params={"per_page": 100}, headers=_RU)
    assert feed.status_code == 200, feed.text
    mine = [p for p in feed.json()["items"] if p["id"] == post["id"]]
    assert [p["title"] for p in mine] == ["Новости урожая"]

    # The staff list answers the editor's shape in the reader's language.
    listing = await client.get(
        "/api/v1/staff/posts",
        params={"per_page": 100},
        headers={**auth_headers(admin_token), **_RU},
    )
    staff_post = next(p for p in listing.json()["items"] if p["id"] == post["id"])
    assert staff_post["title"] == "Новости урожая"
    assert staff_post["base"]["title"] == title


# ---------------------------------------------------------------------------
# 6: search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_finds_a_project_by_its_name_in_any_language(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The Russian name finds the project for an English reader and the
    English name for a Russian one; the answer is in the reader's language.
    A LIKE metacharacter in a translation is matched literally."""
    _, admin_token = await create_admin_user(client, db_session)
    tag = _tag()
    company = await _project(
        client,
        admin_token,
        name=f"Sunrise Farm {tag}",
        translations={"ru": {"name": f"Ферма Рассвет_{tag} 50%"}},
    )
    other = await _project(client, admin_token, name=f"Other Farm {tag}")

    found = await client.get(
        "/api/v1/public/companies", params={"search": f"рассвет_{tag}"}, headers=_EN
    )
    assert [c["id"] for c in found.json()["items"]] == [company["id"]]
    assert found.json()["items"][0]["name"] == f"Sunrise Farm {tag}"

    found = await client.get(
        "/api/v1/public/companies", params={"search": f"sunrise farm {tag}"}, headers=_RU
    )
    assert [c["name"] for c in found.json()["items"]] == [f"Ферма Рассвет_{tag} 50%"]

    both = await client.get("/api/v1/public/companies", params={"search": tag}, headers=_EN)
    assert {c["id"] for c in both.json()["items"]} == {company["id"], other["id"]}

    # "%" is literal: "Рассвет_<tag> 5%" is not a substring of "... 50%".
    none = await client.get(
        "/api/v1/public/companies", params={"search": f"Рассвет_{tag} 5%"}, headers=_RU
    )
    assert none.json()["items"] == []
    literal = await client.get(
        "/api/v1/public/companies", params={"search": "50%"}, headers=_RU
    )
    assert company["id"] in [c["id"] for c in literal.json()["items"]]


# ---------------------------------------------------------------------------
# 7: picture variants
# ---------------------------------------------------------------------------


def _key_of(url: str) -> str:
    from urllib.parse import urlsplit

    from app.core.config import settings

    return urlsplit(url).path.split(f"/{settings.storage_bucket}/", 1)[1]


@pytest.mark.asyncio
async def test_a_cover_variant_is_served_to_its_reader_and_the_common_one_to_the_rest(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """REPEAT: common and ru variant side by side, read by ru, en and fr.
    SHORTAGE: only the cover has a variant -- the logo falls back to the
    common file for the ru reader. Removal falls back to the common file."""
    _, admin_token = await create_admin_user(client, db_session)
    company = await _project(client, admin_token)
    cid = company["id"]
    headers = auth_headers(admin_token)
    base_url = f"/api/v1/staff/companies/{cid}/media"
    for slot in ("cover", "logo"):
        resp = await client.put(
            f"{base_url}/{slot}", files={"file": (f"{slot}.png", _PNG, "image/png")}, headers=headers
        )
        assert resp.status_code == 200, resp.text
    resp = await client.put(
        f"{base_url}/cover?language=ru",
        files={"file": ("cover.png", _PNG + b"ru", "image/png")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    variants = resp.json()["image_variants"]
    assert _key_of(variants["en"]["cover_url"]) == f"companies/{cid}/media/cover.png"
    assert _key_of(variants["ru"]["cover_url"]) == f"companies/{cid}/media/ru/cover.png"
    assert variants["ru"]["logo_url"] is None

    ru = (await _public(client, cid, _RU)).json()
    en = (await _public(client, cid, _EN)).json()
    fr = (await _public(client, cid, _FR)).json()
    assert _key_of(ru["cover_url"]) == f"companies/{cid}/media/ru/cover.png"
    assert _key_of(ru["logo_url"]) == f"companies/{cid}/media/logo.png"
    for body in (en, fr):
        assert _key_of(body["cover_url"]) == f"companies/{cid}/media/cover.png"

    # The editor reading in Russian still sees the common file as common.
    staff = await _staff_view(client, admin_token, cid, _RU)
    assert _key_of(staff["cover_url"]) == f"companies/{cid}/media/ru/cover.png"
    assert _key_of(staff["image_variants"]["en"]["cover_url"]) == f"companies/{cid}/media/cover.png"

    # Removing the variant: Russian readers fall back to the common file.
    resp = await client.delete(f"{base_url}/cover?language=ru", headers=headers)
    assert resp.status_code == 204, resp.text
    ru = (await _public(client, cid, _RU)).json()
    assert _key_of(ru["cover_url"]) == f"companies/{cid}/media/cover.png"
    # Removing it again: nothing there.
    resp = await client.delete(f"{base_url}/cover?language=ru", headers=headers)
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_a_variant_without_a_common_file_shows_only_to_its_reader(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """EMPTINESS: no common logo, a Russian one -> ru sees it, en sees none."""
    _, admin_token = await create_admin_user(client, db_session)
    company = await _project(client, admin_token)
    resp = await client.put(
        f"/api/v1/staff/companies/{company['id']}/media/logo?language=ru",
        files={"file": ("logo.png", _PNG, "image/png")},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert (await _public(client, company["id"], _RU)).json()["logo_url"]
    assert (await _public(client, company["id"], _EN)).json()["logo_url"] is None


@pytest.mark.parametrize(("language", "status"), [("en", 400), ("RU", 422), ("rus", 422)])
@pytest.mark.asyncio
async def test_a_variant_language_must_be_another_two_letter_code(
    client: AsyncClient, db_session: AsyncSession, language: str, status: int
) -> None:
    """English is the common file, never a variant (400 from the service);
    a code of the wrong form never reaches it (422)."""
    _, admin_token = await create_admin_user(client, db_session)
    company = await _project(client, admin_token)
    resp = await client.put(
        f"/api/v1/staff/companies/{company['id']}/media/cover?language={language}",
        files={"file": ("cover.png", _PNG, "image/png")},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == status, resp.text


@pytest.mark.asyncio
async def test_product_and_roadmap_covers_have_language_variants(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, admin_token = await create_admin_user(client, db_session)
    headers = auth_headers(admin_token)
    company, product = await _create_company_with_product(client, admin_token)
    cid, pid = company["id"], product["id"]

    url = f"/api/v1/staff/companies/{cid}/products/{pid}/cover"
    for query, payload in (("", _PNG), ("?language=ru", _PNG + b"ru")):
        resp = await client.put(
            url + query, files={"file": ("c.png", payload, "image/png")}, headers=headers
        )
        assert resp.status_code == 200, resp.text
    ru = (await client.get(f"/api/v1/public/products/{pid}", headers=_RU)).json()
    en = (await client.get(f"/api/v1/public/products/{pid}", headers=_EN)).json()
    assert _key_of(ru["cover_url"]) == f"companies/{cid}/products/{pid}/ru/cover.png"
    assert _key_of(en["cover_url"]) == f"companies/{cid}/products/{pid}/cover.png"

    resp = await client.post(
        f"/api/v1/staff/companies/{cid}/roadmap",
        json={"kind": "announcement", "title": "Opening"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    iid = resp.json()["id"]
    resp = await client.put(
        f"/api/v1/staff/companies/{cid}/roadmap/{iid}/cover?language=ru",
        files={"file": ("c.png", _PNG, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["image_variants"]["en"] == {"cover_url": None}
    ru = (await _public(client, cid, _RU)).json()
    en = (await _public(client, cid, _EN)).json()
    assert _key_of(ru["roadmap"][0]["cover_url"]) == f"companies/{cid}/roadmap/{iid}/ru/cover.png"
    assert en["roadmap"][0]["cover_url"] is None


# ---------------------------------------------------------------------------
# 8: documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_documents_name_the_project_in_the_templates_language(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agreement and a certificate rendered from a Russian template carry
    the Russian names; the legal name stays English (it is not translated);
    an English template carries the English names."""
    _, admin_token = await create_admin_user(client, db_session)
    company, product = await _create_company_with_product(client, admin_token)
    resp = await client.patch(
        f"/api/v1/staff/companies/{company['id']}",
        json={"translations": {"ru": {"name": "Регрессия"}}},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.patch(
        f"/api/v1/staff/products/{product['id']}",
        json={"translations": {"ru": {"name": "Пакет"}}},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    inv_id, sale_id = await _create_investor_and_purchase(client, db_session, product["id"])

    async def _html(_prefix: str) -> str:
        return "{{ company_name }}|{{ company_legal_name }}|{{ product_name }}"

    async def _assets(_prefix: str, _files: list[str]):
        return lambda _name: ""

    monkeypatch.setattr("app.modules.purchases.agreement_service.get_template_html_cached", _html)
    monkeypatch.setattr("app.modules.purchases.agreement_service.make_asset_data_uri_func", _assets)

    data = await load_agreement_data(sale_id, inv_id, db_session)
    data.purchase.agreement_html = None
    stored = data.template
    for language, expected in (
        ("ru", "Регрессия|Regression Co|Пакет"),
        ("en", "Regression Co|Regression Co|Regression Package"),
    ):
        data.template = SimpleNamespace(
            storage_prefix=stored.storage_prefix, asset_files=stored.asset_files, language=language
        )
        assert await render_agreement_html(data, db_session) == expected

    async def _cert_html(_prefix: str) -> str:
        return "{{ company_name }}"

    monkeypatch.setattr(ownership_certificate_service, "get_template_html_cached", _cert_html)
    monkeypatch.setattr(ownership_certificate_service, "make_asset_data_uri_func", _assets)
    ownership = await load_ownership_data(UUID(company["id"]), inv_id, db_session)
    for language, expected in (("ru", "Регрессия"), ("en", "Regression Co")):

        # The template's language, whatever the investor's (the call
        # passes `language=` itself, so the bound value has its own name).
        async def _template(*_args, _bound=language, **_kwargs):
            return SimpleNamespace(storage_prefix="x", asset_files=[], language=_bound)

        monkeypatch.setattr(ownership_certificate_service, "find_active_template", _template)
        assert await render_ownership_html(ownership, db_session) == expected


# ---------------------------------------------------------------------------
# 9: the seed -- refusals before any write (the run itself, with its
#    translations, variant and zero second run, is in test_seed.py's
#    shipped-profile test)
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_DEMO_DIR = _FIXTURES / "seed_project"


def _seed_profile(project: dict) -> dict:
    return {"marker": f"pytest_tr_{_tag()}", "companies": [project]}


def _shipped_project() -> dict:
    project = json.loads((_FIXTURES / "seed_project.json").read_text(encoding="utf-8"))
    project["email_local"] = f"demo-{_tag()}"
    return project


@pytest.mark.parametrize(
    ("breakage", "needle"),
    [
        ("media_en", "English is the common file"),
        ("bad_code_dir", "is not a two-letter lowercase language code"),
        ("orphan_variant", "which is no picture of this profile"),
        ("roadmap_orphan", "roadmap/de/nowhere.png would be a variant"),
        ("dir_in_variant", "is not a file"),
        ("big_variant_logo", "over the 1048576-byte limit"),
        ("bad_text_language", "language 'ru-RU' is not a two-letter"),
        ("long_translation", "longer than 500 characters"),
    ],
)
def test_the_seed_refuses_a_bad_language_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, breakage: str, needle: str
) -> None:
    """validate_profile() is the pre-write check: a refusal there leaves no
    row and no object (test_seed.py pins that for every refusal)."""
    root = tmp_path / "projects"
    shutil.copytree(_DEMO_DIR, root / "demo")
    monkeypatch.setattr(seed, "PROJECTS_DIR", root)
    monkeypatch.setattr(seed_settings, "frontend_base_url", "https://seedtest.example.com")
    demo = root / "demo"
    project = _shipped_project()

    if breakage == "media_en":
        (demo / "media" / "en").mkdir()
        (demo / "media" / "en" / "logo.png").write_bytes(_PNG)
    elif breakage == "bad_code_dir":
        (demo / "media" / "RU").mkdir()
        (demo / "media" / "RU" / "logo.png").write_bytes(_PNG)
    elif breakage == "orphan_variant":
        (demo / "media" / "ru" / "banner.png").write_bytes(_PNG)
    elif breakage == "roadmap_orphan":
        (demo / "roadmap" / "de").mkdir()
        (demo / "roadmap" / "de" / "nowhere.png").write_bytes(_PNG)
    elif breakage == "dir_in_variant":
        (demo / "media" / "ru" / "cover.png").unlink()
        (demo / "media" / "ru" / "cover.png").mkdir()
    elif breakage == "big_variant_logo":
        (demo / "media" / "ru" / "logo.png").write_bytes(_PNG + b"\0" * (1024 * 1024))
    elif breakage == "bad_text_language":
        project["name"]["ru-RU"] = "Демо"
    elif breakage == "long_translation":
        project["products"][0]["name"]["ru"] = "x" * 501

    with pytest.raises(seed.SeedRefusedError) as excinfo:
        seed.validate_profile(_seed_profile(project))
    assert needle in str(excinfo.value)


def test_the_seed_reads_variants_beside_the_pictures_they_vary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REPEAT: two languages of one picture, and a roadmap cover variant;
    the shipped folder's media/ru/cover.png among them. EMPTINESS: a
    project with no language folder has no variants."""
    root = tmp_path / "projects"
    shutil.copytree(_DEMO_DIR, root / "demo")
    monkeypatch.setattr(seed, "PROJECTS_DIR", root)
    demo = root / "demo"
    (demo / "media" / "de").mkdir()
    (demo / "media" / "de" / "cover.png").write_bytes(_PNG)
    (demo / "roadmap" / "ru").mkdir()
    (demo / "roadmap" / "ru" / "launch.png").write_bytes(_PNG)
    project = _shipped_project()
    project["key"] = "demo"

    variants = seed._picture_variants(project, "demo")
    assert {k: sorted(v) for k, v in variants.items()} == {
        "media/cover.png": ["de", "ru"],
        "roadmap/launch.png": ["ru"],
    }
    assert seed._translations(
        project, ("name", "description"), "company_profiles", "demo"
    ) == {"ru": {"name": "Демо-проект", "description": project["description"]["ru"]}}

    shutil.rmtree(demo / "media" / "ru")
    shutil.rmtree(demo / "media" / "de")
    shutil.rmtree(demo / "roadmap" / "ru")
    assert seed._picture_variants(project, "demo") == {}
