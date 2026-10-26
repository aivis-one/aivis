# =============================================================================
# AIVIS.ONE Backend -- unit tests for the NUTREEX entry of the seed profile
# =============================================================================
#
# The default seed profile carries NUTREEX beside SANKORD: its texts in
# English and Russian, the terms of its lot, four portfolio products with
# bonus tiers and instalment plans, and six roadmap items without dates.
# They read the profile and the project folder as files, so they need no
# database. The pictures of NUTREEX do not exist yet: the profile names
# none, the folder holds none, and the seed loads the project without them;
# they arrive by sync_project_package.py and the next seed run.
# =============================================================================

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import scripts.seed as seed

_FOLDER = Path(seed.__file__).resolve().parent / "templates" / "projects" / "nutreex"
_CYRILLIC = {chr(c) for c in range(0x0400, 0x0500)}


@pytest.fixture(scope="module")
def nutreex() -> dict[str, Any]:
    profile = seed.load_profile("default")
    (entry,) = [c for c in profile["companies"] if c["key"] == "nutreex"]
    return entry


def _has_cyrillic(text: str) -> bool:
    return any(ch in _CYRILLIC for ch in text)


def test_the_account_and_the_terms(nutreex: dict[str, Any]) -> None:
    assert nutreex["email_local"] == "nutreex"
    assert seed._local_of(nutreex) == "nutreex"
    assert (nutreex["first_name"], nutreex["last_name"], nutreex["country"]) == (
        "NUTREEX",
        "Team",
        "GE",
    )
    assert nutreex["name"] == {"en": "NUTREEX", "ru": "NUTREEX"}
    # A lot is 100 parts at 10 cents: a part is 0.1 cent, 0.001 USD.
    assert nutreex["price_per_unit_cents"] == 10
    assert nutreex["shares_per_option"] == 100
    assert nutreex["total_supply"] == 10_000_000
    assert nutreex["total_supply"] * nutreex["shares_per_option"] == 1_000_000_000
    # The valuation the cabinet shows: every lot at the lot's price.
    assert nutreex["total_supply"] * nutreex["price_per_unit_cents"] == 100_000_000
    assert nutreex["pool"] == {"equity_percent": 25}
    assert nutreex["distribution_config"] == {
        "company_pct": 0.83,
        "agent_levels": [0.1, 0.03, 0.01],
    }


def test_the_description_has_both_languages(nutreex: dict[str, Any]) -> None:
    description = nutreex["description"]
    assert description["en"].strip() and not _has_cyrillic(description["en"])
    assert _has_cyrillic(description["ru"])


def test_four_portfolios_with_the_same_prices_and_tiers_as_the_platform(
    nutreex: dict[str, Any],
) -> None:
    price = nutreex["price_per_unit_cents"]
    products = nutreex["products"]
    assert [p["name"]["en"] for p in products] == [
        "Portfolio 200 USD",
        "Portfolio 1,000 USD",
        "Portfolio 5,000 USD",
        "Portfolio 25,000 USD",
    ]
    assert [p["package_size"] * price for p in products] == [
        20_000, 100_000, 500_000, 2_500_000,
    ]
    assert [
        [(b["threshold_cents"], b["bonus_units_percent"]) for b in p["purchase_config"]["bonuses"]]
        for p in products
    ] == [[], [(100_000, 5)], [(500_000, 10)], [(2_500_000, 20)]]
    for product in products:
        assert product["description"]["en"].strip()
        assert "NUTREEX" in product["description"]["en"]
        assert _has_cyrillic(product["description"]["ru"])
        assert product["cover"] == "media/product.png"
        total = product["package_size"] * price
        plans = product["installments"]
        assert [p["name"]["en"] for p in plans] == ["6 months", "12 months", "24 months"]
        for plan in plans:
            tranches = plan["plan_config"]["tranches"]
            assert sum(t["amount_cents"] for t in tranches) == total
            assert sum(t["units_percent"] for t in tranches) == 100


def test_six_roadmap_items_without_dates_in_both_languages(
    nutreex: dict[str, Any],
) -> None:
    roadmap = nutreex["roadmap"]
    assert [i["key"] for i in roadmap] == ["s1", "s2", "s3", "s4", "s5", "s6"]
    assert [i["status"] for i in roadmap] == ["in_progress"] + ["planned"] * 5
    assert len({i["title"]["en"] for i in roadmap}) == 6
    for item in roadmap:
        assert "target_date" not in item and "cover" not in item
        assert _has_cyrillic(item["title"]["ru"])
        assert _has_cyrillic(item["description"]["ru"])


def test_the_media_exist_and_the_cover_has_a_russian_variant(nutreex: dict[str, Any]) -> None:
    for slot in ("logo", "logo_dark", "cover"):
        assert (_FOLDER / nutreex[slot]).is_file(), slot
    for product in nutreex["products"]:
        assert (_FOLDER / product["cover"]).is_file()
    assert (_FOLDER / "media" / "ru" / "cover.png").is_file()


def test_texts_go_to_the_base_columns_and_the_translations(
    nutreex: dict[str, Any],
) -> None:
    assert seed._text(nutreex["name"], "name") == "NUTREEX"
    translations = seed._translations(
        nutreex, ("name", "description"), "company_profiles", "company"
    )
    assert translations["ru"]["description"] == nutreex["description"]["ru"]
    for item in nutreex["roadmap"]:
        item_translations = seed._translations(
            item, ("title", "description"), "company_roadmap_items", "roadmap"
        )
        assert item_translations["ru"]["title"] == item["title"]["ru"]


def test_no_draft_or_internal_marker_in_the_project_texts(
    nutreex: dict[str, Any],
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
    for text in texts([nutreex["description"], nutreex["products"], nutreex["roadmap"]]):
        assert not any(word.lower() in text.lower() for word in banned), text
    # the cabinet speaks of parts of the project, never of investment
    for text in texts([nutreex["products"]]):
        assert "invest" not in text.lower(), text
