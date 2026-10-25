# =============================================================================
# AIVIS.ONE Backend -- the documents state Parts, the price of a Part, the total
# =============================================================================
#
# WHAT THIS GUARDS. A buyer never sees the lot. The purchase agreement, the
# instalment subcontract, the gift certificate and the ownership certificate
# state the count of Parts (lots x the project's Parts per lot), the price of
# one Part with three decimals and the total in dollars and cents, and the
# arithmetic closes in whole cents.
#
# NO DATABASE. The helpers are pure; the shipped templates are rendered with
# the document environment against a context shaped like the renderers' own.
# =============================================================================

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import meta

from app.modules.companies.constants import TEMPLATE_PLACEHOLDERS, DocumentTemplateKind
from app.modules.purchases.document_utils import (
    build_document_environment,
    format_cents,
    format_part_price,
    parts_of,
)

TEMPLATES = Path(__file__).resolve().parents[1] / "scripts" / "templates" / "_default"
LANGUAGES = ("en", "ru", "de", "ar")


# -- the helpers ------------------------------------------------------------


def test_parts_are_lots_times_parts_per_lot() -> None:
    assert parts_of(4, 25) == 100
    assert parts_of(0, 25) == 0
    assert parts_of(3, 1) == 3


@pytest.mark.parametrize(
    ("lot_cents", "per_lot", "expected"),
    [
        (10, 25, "0.004"),
        (100, 1, "1.000"),
        (1, 3, "0.003"),
        (5, 3, "0.017"),
        (118750, 1250, "0.950"),
        (10, 0, "0.000"),
    ],
)
def test_part_price_has_three_decimals(lot_cents: int, per_lot: int, expected: str) -> None:
    assert format_part_price(lot_cents, per_lot) == expected


def test_total_closes_in_whole_cents() -> None:
    lots, lot_cents, per_lot = 4, 10, 25
    parts = parts_of(lots, per_lot)
    total_cents = lots * lot_cents
    # 100 parts at 0.004 USD is 0.40 USD: the total the purchase carries.
    assert parts * 4 == total_cents * 10
    assert format_cents(total_cents) == "0.40"


# -- the shipped templates --------------------------------------------------


def _read(kind: str, language: str) -> str:
    return (TEMPLATES / kind / language / "template.html").read_text(encoding="utf-8")


def _purchase_context() -> dict[str, object]:
    return {
        "investor_name": "Anna Ivanova",
        "investor_email": "anna@example.com",
        "company_name": "Acme",
        "company_legal_name": "Acme",
        "company_logo_url": None,
        "product_name": "Pack",
        "units": 4,
        "parts": parts_of(4, 25),
        "price_per_part_display": format_part_price(10, 25),
        "paid_cents": 40,
        "paid_display": format_cents(40),
        "price_per_unit_cents": 10,
        "price_per_unit_display": format_cents(10),
        "legal_basis": "sale",
        "purchase_date": "October 23, 2026",
        "issue_date": "October 23, 2026",
        "withdrawal_end_date": "November 6, 2026",
        "buyer_agreement_accepted_at": "",
        "buyer_agreement_annex": "",
        "certificate_number": "ABC123",
        "account_number": "A1B2C3",
        "bonus_parts": parts_of(1, 25),
        "purchase_type": "sale",
        "tranche_number": 0,
        "tranche_count": 0,
    }


def _ownership_context() -> dict[str, object]:
    return {
        "investor_name": "Anna Ivanova",
        "company_name": "Acme",
        "company_logo_url": None,
        "total_units": 5,
        "sale_units": 4,
        "gift_units": 1,
        "total_parts": parts_of(5, 25),
        "sale_parts": parts_of(4, 25),
        "gift_parts": parts_of(1, 25),
        "total_paid_cents": 40,
        "total_paid_display": format_cents(40),
        "current_value_cents": 50,
        "current_value_display": format_cents(50),
        "as_of_date": "October 23, 2026",
        "purchases": [
            {
                "units": 4,
                "parts": parts_of(4, 25),
                "price_per_part_display": format_part_price(10, 25),
                "paid_cents": 40,
                "paid_display": format_cents(40),
                "date": "October 23, 2026",
                "purchase_type": "sale",
                "tranche_number": 0,
                "tranche_count": 0,
                "legal_basis": "sale",
            }
        ],
    }


def _render(kind: str, language: str, context: dict[str, object]) -> str:
    env = build_document_environment(lambda _name: "")
    return env.from_string(_read(kind, language)).render(**context)


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("kind", ["purchase_agreement", "installment_subcontract"])
def test_purchase_documents_state_parts_part_price_and_total(kind: str, language: str) -> None:
    html = _render(kind, language, _purchase_context())
    assert ">100<" in html  # 4 lots x 25 parts
    assert "0.004" in html  # the price of one part
    assert "0.40" in html  # the total, dollars and cents
    assert ">4<" not in html  # the lot count is not printed as the quantity


@pytest.mark.parametrize("language", ["en", "ru"])
def test_gift_certificate_states_parts(language: str) -> None:
    html = _render("gift_certificate", language, _purchase_context())
    assert ">100<" in html
    assert ">4<" not in html


@pytest.mark.parametrize("language", LANGUAGES)
def test_ownership_certificate_states_parts_in_totals_and_rows(language: str) -> None:
    html = _render("ownership_certificate", language, _ownership_context())
    assert ">125<" in html  # held: 5 lots x 25
    assert ">100<" in html  # bought, and the history row
    assert ">25<" in html  # received as bonus or gift
    assert "0.40" in html


@pytest.mark.parametrize(
    ("kind", "enum"),
    [
        ("purchase_agreement", DocumentTemplateKind.PURCHASE_AGREEMENT),
        ("gift_certificate", DocumentTemplateKind.GIFT_CERTIFICATE),
        ("installment_subcontract", DocumentTemplateKind.INSTALLMENT_SUBCONTRACT),
        ("ownership_certificate", DocumentTemplateKind.OWNERSHIP_CERTIFICATE),
    ],
)
@pytest.mark.parametrize("language", LANGUAGES)
def test_shipped_templates_read_only_declared_variables(
    kind: str, enum: DocumentTemplateKind, language: str
) -> None:
    env = build_document_environment(None)
    used = meta.find_undeclared_variables(env.parse(_read(kind, language)))
    allowed = TEMPLATE_PLACEHOLDERS[enum] | {"asset_data_uri"}
    assert used <= allowed, sorted(used - allowed)
