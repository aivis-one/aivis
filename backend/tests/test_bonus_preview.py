"""Bonus preview: the pre-payment totals follow the purchase's own rule.

Pure-function tests -- no database needed.
"""

import uuid
from datetime import UTC, datetime

from app.modules.processors.base import PurchaseContext
from app.modules.processors.gift import GiftProcessor, total_bonus_units
from app.modules.purchases.service import compute_bonus_preview

BONUSES = [
    {"condition": "always", "bonus_units_percent": 5},
    {
        "condition": "purchase_amount_gte",
        "threshold_cents": 100_000,
        "bonus_units_percent": 10,
    },
    {
        "condition": "portfolio_size_gte",
        "threshold_cents": 500_000,
        "bonus_units_percent": 20,
    },
]


def _context(units: int, price: int, bonuses: list[dict]) -> PurchaseContext:
    return PurchaseContext(
        investor_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        company_user_id=uuid.uuid4(),
        platform_user_id=uuid.uuid4(),
        amount_cents=units * price,
        units=units,
        price_per_unit_cents=price,
        distribution_config={},
        purchase_config_bonuses=bonuses,
        origin_payment_id=None,
        frozen_until=None,
        triggered_at=datetime.now(UTC),
    )


def test_no_bonuses():
    assert compute_bonus_preview([], 100, 1000, 0) == (0, 0.0)


def test_always_only():
    # amount 50_000 < 100_000; portfolio small -> only "always": floor(100*5/100)
    assert compute_bonus_preview(BONUSES, 100, 500, 0) == (5, 5.0)


def test_purchase_amount_condition():
    # amount 100_000 meets the purchase_amount_gte threshold.
    assert compute_bonus_preview(BONUSES, 100, 1000, 0) == (15, 15.0)


def test_portfolio_condition_counts_this_purchase():
    # portfolio 450_000 + amount 100_000 >= 500_000 -> all three apply.
    assert compute_bonus_preview(BONUSES, 100, 1000, 450_000) == (35, 35.0)


def test_unit_floor():
    assert compute_bonus_preview(
        [{"condition": "always", "bonus_units_percent": 5}], 10, 100, 0
    ) == (0, 0.0)


def test_unknown_condition_skipped():
    assert compute_bonus_preview(
        [{"condition": "weird", "bonus_units_percent": 50}], 100, 100, 0
    ) == (0, 0.0)


def test_preview_equals_processor_units():
    """The preview's units equal the units the gift processor grants."""
    for units, price, portfolio in [
        (100, 500, 0),
        (100, 1000, 0),
        (100, 1000, 450_000),
        (37, 4000, 10),
    ]:
        ctx = _context(units, price, BONUSES)
        granted = sum(
            t.units for t in GiftProcessor(portfolio).process(ctx)
        )
        preview_units, _ = total_bonus_units(
            BONUSES, units, units * price, portfolio
        )
        assert preview_units == granted


def test_register_request_language_validated():
    import pytest
    from pydantic import ValidationError

    from app.modules.auth.schemas import EmailRegisterRequest

    base = {"email": "a@example.com", "password": "password123"}
    assert EmailRegisterRequest(**base).language is None
    assert EmailRegisterRequest(**base, language="de").language == "de"
    with pytest.raises(ValidationError):
        EmailRegisterRequest(**base, language="xx")
