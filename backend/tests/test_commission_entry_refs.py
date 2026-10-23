# =============================================================================
# AIVIS.ONE Backend -- Commission entry references (DB-free)
# =============================================================================
#
# A commission entry names the partner and the purchase in the short id form
# the cabinet shows ids in. These tests need no database.
# =============================================================================

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.commissions.schemas import CommissionEntry
from app.modules.commissions.service import short_id


def test_short_id_is_first_eight_characters() -> None:
    value = UUID("12345678-aaaa-bbbb-cccc-1234567890ab")
    assert short_id(value) == "12345678"


def test_entry_carries_partner_and_purchase_refs() -> None:
    entry = CommissionEntry(
        id=uuid4(),
        type="commission",
        amount_cents=100,
        status="confirmed",
        created_at=datetime.now(UTC),
        level=1,
        investor_short_id="12345678",
        purchase_short_id="87654321",
    )
    dumped = entry.model_dump()
    assert dumped["investor_short_id"] == "12345678"
    assert dumped["purchase_short_id"] == "87654321"


def test_refs_default_to_none() -> None:
    entry = CommissionEntry(
        id=uuid4(),
        type="volume_bonus",
        amount_cents=100,
        status="frozen",
        created_at=datetime.now(UTC),
    )
    assert entry.investor_short_id is None
    assert entry.purchase_short_id is None
