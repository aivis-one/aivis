# =============================================================================
# AIVIS.ONE Backend -- unit tests for the SANKORD entry of the seed profile
# =============================================================================
#
# WHAT THESE TESTS ARE FOR. The default seed profile carries a second
# project, SANKORD: its texts in English and Russian, four portfolio
# products with their bonus tiers and instalment plans, a roadmap and its
# pictures. They read the profile and the project folder as files and
# assert the mapping, so they need no database. What only a database can
# show -- the rows and the stored objects of a real seed run -- is covered
# by test_seed.py, which needs the test stand.
# =============================================================================

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import scripts.seed as seed

_SCRIPTS = Path(seed.__file__).resolve().parent
_FOLDER = _SCRIPTS / "templates" / "projects" / "sankord"
_CYRILLIC = {chr(c) for c in range(0x0400, 0x0500)}


@pytest.fixture(scope="module")
def profile() -> dict[str, Any]:
    return seed.load_profile("default")


@pytest.fixture(scope="module")
def sankord(profile: dict[str, Any]) -> dict[str, Any]:
    (entry,) = [c for c in profile["companies"] if c["key"] == "sankord"]
    return entry


def _has_cyrillic(text: str) -> bool:
    return any(ch in _CYRILLIC for ch in text)


def test_the_account_and_the_project_economics(sankord: dict[str, Any]) -> None:
    assert sankord["email_local"] == "sankord"
    assert sankord["name"] == {"en": "SANKORD", "ru": "SANKORD"}
    # A lot is 25 parts at 10 cents: a part is 0.4 cent.
    assert sankord["price_per_unit_cents"] == 10
    assert sankord["shares_per_option"] == 25
    assert sankord["price_per_unit_cents"] / sankord["shares_per_option"] == 0.4
    assert sankord["total_supply"] == 40_000_000
    assert sankord["pool"] == {"equity_percent": 25}
    assert sankord["total_supply"] * sankord["shares_per_option"] == 1_000_000_000
    assert sankord["distribution_config"] == {
        "company_pct": 0.83,
        "agent_levels": [0.1, 0.03, 0.01],
    }


def test_the_description_has_both_languages(sankord: dict[str, Any]) -> None:
    description = sankord["description"]
    assert description["en"].strip() and not _has_cyrillic(description["en"])
    assert _has_cyrillic(description["ru"])


def test_four_portfolio_products_with_prices_and_bonus_tiers(
    sankord: dict[str, Any],
) -> None:
    price = sankord["price_per_unit_cents"]
    products = sankord["products"]
    assert [p["name"]["en"] for p in products] == [
        "Portfolio 200 USD",
        "Portfolio 1,000 USD",
        "Portfolio 5,000 USD",
        "Portfolio 25,000 USD",
    ]
    assert [p["name"]["ru"] for p in products] == [
        "Портфель 200 USD",
        "Портфель 1 000 USD",
        "Портфель 5 000 USD",
        "Портфель 25 000 USD",
    ]
    # Prices in cents: package_size lots at the lot price.
    assert [p["package_size"] * price for p in products] == [
        20_000, 100_000, 500_000, 2_500_000,
    ]
    tiers = [p["purchase_config"]["bonuses"] for p in products]
    assert tiers[0] == []
    assert [
        (b["condition"], b["threshold_cents"], b["bonus_units_percent"], b["funded_by"])
        for (b,) in tiers[1:]
    ] == [
        ("purchase_amount_gte", 100_000, 5, "company"),
        ("purchase_amount_gte", 500_000, 10, "company"),
        ("purchase_amount_gte", 2_500_000, 20, "company"),
    ]
    for product in products:
        assert product["description"]["en"].strip()
        assert not _has_cyrillic(product["description"]["en"])
        assert _has_cyrillic(product["description"]["ru"])
        assert product["cover"] == "media/product.png"


def test_every_product_has_three_instalment_plans_that_add_up(
    sankord: dict[str, Any],
) -> None:
    price = sankord["price_per_unit_cents"]
    for product in sankord["products"]:
        total = product["package_size"] * price
        plans = product["installments"]
        assert [p["name"] for p in plans] == ["6 months", "12 months", "24 months"]
        for plan in plans:
            tranches = plan["plan_config"]["tranches"]
            assert sum(t["amount_cents"] for t in tranches) == total
            assert sum(t["units_percent"] for t in tranches) == 100


def test_the_roadmap_has_both_languages_and_unique_keys(
    sankord: dict[str, Any],
) -> None:
    roadmap = sankord["roadmap"]
    assert len(roadmap) == 26
    assert len({i["key"] for i in roadmap}) == 26
    assert len({i["title"]["en"] for i in roadmap}) == 26
    for item in roadmap:
        assert not _has_cyrillic(item["title"]["en"])
        assert _has_cyrillic(item["title"]["ru"])
        assert not _has_cyrillic(item["description"]["en"])
        assert _has_cyrillic(item["description"]["ru"])
        # Done items keep their month; items ahead carry no date.
        if item["status"] == "completed":
            assert item["target_date"]
        else:
            assert "target_date" not in item


def test_the_media_exist_and_the_cover_has_a_russian_variant(
    sankord: dict[str, Any],
) -> None:
    for slot in ("logo", "logo_dark", "cover"):
        assert (_FOLDER / sankord[slot]).is_file(), slot
    for product in sankord["products"]:
        assert (_FOLDER / product["cover"]).is_file()
    assert (_FOLDER / "media" / "ru" / "cover.png").is_file()
    # the seed finds the Russian cover as the variant of the common one
    variants = seed._variants_of(sankord, sankord["cover"])
    assert set(variants) == {"ru"}


def test_texts_go_to_the_base_columns_and_the_translations(
    sankord: dict[str, Any],
) -> None:
    assert seed._text(sankord["name"], "name") == "SANKORD"
    translations = seed._translations(
        sankord, ("name", "description"), "company_profiles", "company"
    )
    assert translations["ru"]["description"] == sankord["description"]["ru"]
    for product in sankord["products"]:
        english = seed._text(product["name"], "product.name")
        assert english == product["name"]["en"]
        product_translations = seed._translations(
            product, ("name", "description"), "products", "product"
        )
        assert product_translations["ru"]["name"] == product["name"]["ru"]
        assert product_translations["ru"]["description"] == product["description"]["ru"]
    for item in sankord["roadmap"]:
        item_translations = seed._translations(
            item, ("title", "description"), "company_roadmap_items", "roadmap"
        )
        assert item_translations["ru"]["title"] == item["title"]["ru"]


def test_no_draft_or_internal_marker_in_the_project_texts(
    sankord: dict[str, Any],
) -> None:
    def texts(value: Any):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for v in value.values():
                yield from texts(v)
        elif isinstance(value, list):
            for v in value:
                yield from texts(v)

    banned = ("TODO", "COUNSEL", "TBD", "lorem ipsum", "[draft", "draft:")
    for text in texts([sankord["description"], sankord["products"], sankord["roadmap"]]):
        assert not any(word.lower() in text.lower() for word in banned), text


def test_the_whole_shipped_profile_passes_the_pre_write_checks(
    profile: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """validate_profile is the seed's dry parse: no row and no object is
    written. The host of the front-end address is pinned so the test does
    not depend on the stand's environment."""
    monkeypatch.setattr(seed.settings, "frontend_base_url", "https://stand.example.com")
    seed.validate_profile(profile)
    assert [c["key"] for c in profile["companies"]] == ["demo", "sankord"]
