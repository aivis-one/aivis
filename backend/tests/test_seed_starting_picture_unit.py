# =============================================================================
# AIVIS.ONE Backend -- unit tests for the accounts and the starting picture
# =============================================================================
#
# The default profile's accounts (a support operator, an agent, three
# investors) and the steps of their starting picture, read as a file and
# checked against the arithmetic the application applies, plus the
# refusals of _check_portfolio. No database is needed; the run itself --
# rows, balances, reset -- is in test_seed.py, which needs the test stand.
# =============================================================================

from __future__ import annotations

import copy
import math
from typing import Any

import pytest

import scripts.seed as seed


@pytest.fixture(scope="module")
def profile() -> dict[str, Any]:
    return seed.load_profile("default")


@pytest.fixture(autouse=True)
def host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed.settings, "frontend_base_url", "https://stand.example.com")


def _company(profile: dict[str, Any], key: str) -> dict[str, Any]:
    (entry,) = [c for c in profile["companies"] if c["key"] == key]
    return entry


def _product(company: dict[str, Any], name: str) -> dict[str, Any]:
    (entry,) = [p for p in company["products"] if p["name"]["en"] == name]
    return entry


def _investor(profile: dict[str, Any], local: str) -> dict[str, Any]:
    (entry,) = [i for i in profile["investors"] if i["email_local"] == local]
    return entry


def test_the_accounts_and_their_roles(profile: dict[str, Any]) -> None:
    assert [s["email_local"] for s in profile["staff"]] == ["test01"]
    assert [a["email_local"] for a in profile["agents"]] == ["test03"]
    assert [i["email_local"] for i in profile["investors"]] == ["test02", "test04", "test05"]
    assert [a["key"] for a in profile["agents"]] == ["test03"]
    names = {
        s["email_local"]: (s["first_name"], s["last_name"])
        for s in profile["staff"] + profile["agents"] + profile["investors"]
    }
    assert names == {
        "test01": ("Test", "One"),
        "test02": ("Test", "Two"),
        "test03": ("Test", "Three"),
        "test04": ("Test", "Four"),
        "test05": ("Test", "Five"),
    }
    assert "admin" not in profile, "the seed never makes the admin"
    # test04 and test05 are brought by test03; test02 is nobody's
    assert _investor(profile, "test04")["referred_by_agent"] == "test03"
    assert _investor(profile, "test05")["referred_by_agent"] == "test03"
    assert "referred_by_agent" not in _investor(profile, "test02")


def test_no_money_for_the_operator_and_the_agent(profile: dict[str, Any]) -> None:
    for entry in profile["staff"] + profile["agents"]:
        assert "portfolio" not in entry


def test_the_picture_of_test04_is_the_one_thousand_dollar_portfolio_at_once(
    profile: dict[str, Any],
) -> None:
    sankord = _company(profile, "sankord")
    spec = _investor(profile, "test04")["portfolio"]
    assert spec["deposit_cents"] == 120_000
    assert spec["purchases"] == [{"company": "sankord", "product": "Portfolio 1,000 USD"}]
    product = _product(sankord, "Portfolio 1,000 USD")
    price = product["package_size"] * sankord["price_per_unit_cents"]
    assert price == 100_000
    (bonus,) = product["purchase_config"]["bonuses"]
    bonus_lots = math.floor(product["package_size"] * bonus["bonus_units_percent"] / 100)
    assert bonus_lots == 500 and price >= bonus["threshold_cents"]
    # 200 USD stay with test04; the agent earns 10 percent of the purchase
    assert spec["deposit_cents"] - price == 20_000
    assert round(sankord["distribution_config"]["agent_levels"][0] * price) == 10_000


def test_the_picture_of_test05_is_the_first_payment_of_the_six_month_plan(
    profile: dict[str, Any],
) -> None:
    sankord = _company(profile, "sankord")
    spec = _investor(profile, "test05")["portfolio"]
    assert spec["deposit_cents"] == 20_000
    assert spec["purchases"] == [
        {"company": "sankord", "product": "Portfolio 200 USD", "plan": "6 months"}
    ]
    product = _product(sankord, "Portfolio 200 USD")
    (plan,) = [p for p in product["installments"] if p["name"]["en"] == "6 months"]
    tranches = plan["plan_config"]["tranches"]
    first = tranches[0]
    assert first["amount_cents"] == 3_300 and plan["plan_config"]["bonus_units"] == 0
    assert spec["deposit_cents"] - first["amount_cents"] == 16_700
    assert sum(t["amount_cents"] for t in tranches[1:]) == 16_700
    assert product["package_size"] * first["units_percent"] // 100 == 200
    assert round(sankord["distribution_config"]["agent_levels"][0] * first["amount_cents"]) == 330


def test_the_picture_of_test02_is_a_gift_on_sankord_and_a_portfolio_on_nutreex(
    profile: dict[str, Any],
) -> None:
    spec = _investor(profile, "test02")["portfolio"]
    assert spec["gifts"] == [{"company": "sankord", "product": "Portfolio 200 USD"}]
    assert spec["purchases"] == [{"company": "nutreex", "product": "Portfolio 200 USD"}]
    nutreex = _company(profile, "nutreex")
    price = _product(nutreex, "Portfolio 200 USD")["package_size"] * nutreex["price_per_unit_cents"]
    assert price == 20_000 == spec["deposit_cents"], "the deposit pays for it exactly"


def test_the_profile_passes_the_pre_write_checks(profile: dict[str, Any]) -> None:
    seed.validate_profile(profile)


# ---------------------------------------------------------------- refusals


def _checked(profile: dict[str, Any], portfolio: dict[str, Any]) -> None:
    seed._check_portfolio(profile, portfolio, "investors[0].portfolio")


def test_the_old_count_of_purchases_is_refused_by_name(profile: dict[str, Any]) -> None:
    with pytest.raises(seed.SeedRefusedError, match="old form"):
        _checked(profile, {"deposit_cents": 100, "purchases": 2})


@pytest.mark.parametrize(
    ("portfolio", "needle"),
    [
        ({"deposit_cents": -1}, "deposit_cents must be a whole number"),
        ({"purchases": [{"company": "ghost", "product": "x"}]}, "names no project"),
        ({"purchases": [{"company": "sankord", "product": "ghost"}]}, "names no product"),
        (
            {"deposit_cents": 99_999, "purchases": [{"company": "sankord", "product": "Portfolio 1,000 USD"}]},
            "does not cover",
        ),
        (
            {"deposit_cents": 99_999, "purchases": [{"company": "sankord", "product": "Portfolio 200 USD", "plan": "9 months"}]},
            "names no instalment",
        ),
        ({"gifts": [{"company": "sankord", "product": "Portfolio 200 USD", "lots": 0}]}, "lots must be"),
        ({"gifts": ["x"]}, "must be an object"),
        (
            {
                "deposit_cents": 200_000,
                "purchases": [
                    {"company": "sankord", "product": "Portfolio 200 USD"},
                    {"company": "sankord", "product": "Portfolio 200 USD", "plan": "6 months"},
                ],
            },
            "a product bought at once and on a plan by one investor",
        ),
    ],
)
def test_a_bad_starting_picture_is_refused_before_any_write(
    profile: dict[str, Any], portfolio: dict[str, Any], needle: str
) -> None:
    with pytest.raises(seed.SeedRefusedError, match=needle):
        _checked(profile, portfolio)


def test_a_first_payment_is_covered_by_a_deposit_of_its_amount(profile: dict[str, Any]) -> None:
    _checked(
        profile,
        {
            "deposit_cents": 3_300,
            "purchases": [{"company": "sankord", "product": "Portfolio 200 USD", "plan": "6 months"}],
        },
    )


# ---------------------------------------------------------------- names and addresses


def test_a_package_entry_names_its_account_by_the_local_part_of_its_email() -> None:
    assert seed._local_of({"email": "sankord@example.com"}) == "sankord"
    assert seed._local_of({"email_local": "test01", "email": "x@y.z"}) == "test01"
    assert seed._local_of({}) is None
    with pytest.raises(seed.SeedRefusedError, match="no `email_local`"):
        seed._check_address({}, "companies[0]")
    assert seed._check_address({"email": "sankord@elsewhere.org"}, "c") == "sankord@stand.example.com"


def test_an_installment_name_keeps_english_only() -> None:
    assert seed._plain_name("6 months", "n") == "6 months"
    assert seed._plain_name({"en": "6 months", "ru": "6 мес."}, "n") == "6 months"
    with pytest.raises(seed.SeedRefusedError, match='no "en"'):
        seed._plain_name({"ru": "6 мес."}, "n")


def test_a_company_with_russian_plan_names_passes_the_checks(profile: dict[str, Any]) -> None:
    broken = copy.deepcopy(_company(profile, "sankord"))
    assert isinstance(broken["products"][0]["installments"][0]["name"], dict)
    seed._check_company(broken, "companies[0]")
