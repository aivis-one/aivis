# =============================================================================
# AIVIS.ONE Backend -- Document render context: the document fields (Tests)
# =============================================================================
#
# The four generated documents print what the accepted texts need beyond the
# old field table. Tests cover:
#   1: the Cabinet account number -- the first 8 hex characters of the user's
#      id, uppercased; when two users share the 8 only the LATER one is
#      lengthened, the earlier keeps its number for life (pure, no database)
#   2: the account number reaches the agreement context, and the same render
#      carries purchase_type, bonus_parts and tranche_number / tranche_count
#   3: bonus_parts -- the sum of the ACTIVE bonus rows whose
#      source_purchase_id is the purchase; 0 with none; pending and
#      cancelled rows and another purchase's bonus rows do not count
#   4: purchase_type -- sale, instalment, bonus (sourced, or the instalment
#      completion bonus), gift (staff gift, pending or accepted)
#   5: tranche number and count -- the tranche that paid the purchase and
#      the plan's tranche count; (0, 0) for a purchase that is not a tranche
#   6: the ownership history rows carry each entry's type and its month n of N
#   7: dates in the document's language (ru month names), a cancelled staff
#      gift is a gift
#   8: the Buyer Agreement acceptance time and the Annex: the accepted
#      version's text matched by sha256 to Document.content_hash; a replaced
#      version prints no text
# =============================================================================

import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import jinja2
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import (
    Document,
    DocumentSigning,
    DocumentStatus,
)
from app.modules.installments.constants import (
    InstallmentPlanStatus,
    InstallmentTrancheStatus,
)
from app.modules.installments.models import InstallmentPlan, InstallmentTranche
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.products.models import Product, ProductInstallment
from app.modules.purchases.agreement_service import (
    bonus_parts_of,
    load_agreement_data,
    purchase_type_of,
    render_agreement_html,
    tranche_position,
)
from app.modules.purchases import buyer_agreement_annex
from app.modules.purchases.buyer_agreement_annex import (
    annex_for_document,
    annex_html_from_file,
)
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.document_utils import (
    format_document_date,
    format_document_datetime,
)
from app.modules.purchases.models import Purchase
from app.modules.purchases.ownership_certificate_service import (
    load_ownership_data,
)
from app.modules.users.account_number import (
    account_number_for,
    resolve_account_number,
)
from tests.test_regression_guards import (
    _admin_token,
    _create_company_with_product,
    _create_investor_and_purchase,
)

# ---------------------------------------------------------------------------
# 1: the account number rule (pure)
# ---------------------------------------------------------------------------


def test_account_number_is_the_first_eight_hex_characters_uppercased() -> None:
    user_id = UUID("9f3e7a21-5c4d-4b8e-a1f0-0123456789ab")
    assert account_number_for(user_id, []) == "9F3E7A21"


def test_account_number_ignores_users_with_another_prefix_and_itself() -> None:
    user_id = UUID("9f3e7a21-5c4d-4b8e-a1f0-0123456789ab")
    other = UUID("11111111-5c4d-4b8e-a1f0-0123456789ab")
    assert account_number_for(user_id, [other, user_id]) == "9F3E7A21"


def test_the_earlier_user_keeps_eight_characters_and_the_later_is_lengthened() -> None:
    earlier = UUID("9f3e7a21-5c4d-4b8e-a1f0-0123456789ab")
    later = UUID("9f3e7a21-5c4d-4b8e-a1f0-ffffffffffff")
    n_earlier = account_number_for(earlier, [])
    n_later = account_number_for(later, [earlier])
    assert n_earlier == "9F3E7A21"
    assert len(n_later) > 8
    assert n_later == later.hex[: len(n_later)].upper()
    assert n_earlier != n_later


def test_an_earlier_number_does_not_change_when_a_later_user_collides() -> None:
    earlier = UUID("9f3e7a21-5c4d-4b8e-a1f0-0123456789ab")
    before = account_number_for(earlier, [])
    # The later user is compared against the earlier one; the earlier user
    # is never compared against the later one, so its number is unchanged.
    account_number_for(UUID("9f3e7a21-5c4d-4b8e-a1f0-ffffffffffff"), [earlier])
    assert account_number_for(earlier, []) == before == "9F3E7A21"


def test_a_collision_is_lengthened_only_as_far_as_needed() -> None:
    a = UUID("9f3e7a21-5c4d-4b8e-a1f0-0123456789ab")
    b = UUID("9f3e7a21-5c4e-4b8e-a1f0-0123456789ab")  # differs at char 13
    # "9f3e7a215c4d" vs "9f3e7a215c4e": the 12th character is the first to differ
    assert account_number_for(b, [a]) == b.hex[:12].upper()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _first_investor_purchase(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[dict, UUID, UUID]:
    admin_token = await _admin_token(client, db_session)
    company, product = await _create_company_with_product(client, admin_token)
    inv_id, sale_id = await _create_investor_and_purchase(
        client, db_session, product["id"]
    )
    return company, inv_id, sale_id


async def _add_purchase(
    db_session: AsyncSession,
    sale: Purchase,
    *,
    legal_basis: str,
    status: str,
    units: int,
    source_purchase_id: UUID | None = None,
    paid_cents: int = 0,
) -> Purchase:
    row = Purchase(
        investor_id=sale.investor_id,
        product_id=sale.product_id,
        company_id=sale.company_id,
        legal_basis=legal_basis,
        units=units,
        paid_cents=paid_cents,
        price_per_unit_cents=sale.price_per_unit_cents,
        status=status,
        source_purchase_id=source_purchase_id,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _load_sale(db_session: AsyncSession, sale_id: UUID) -> Purchase:
    return (
        await db_session.execute(select(Purchase).where(Purchase.id == sale_id))
    ).scalar_one()


@pytest.fixture
async def committed_rows(db_session: AsyncSession):
    """Rows a test committed; deleted at its end, in the order appended.

    The test database is shared by the whole run and S-02 counts all of it:
    an active Purchase committed without its ledger pairing would stay behind
    for every later test (test_consistency.py deletes its orphan the same
    way). A test appends only after its commit succeeded.
    """
    rows: list[object] = []
    yield rows
    for row in rows:
        await db_session.delete(row)
        await db_session.flush()
    await db_session.commit()


# ---------------------------------------------------------------------------
# 2: the fields reach the agreement context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agreement_context_carries_the_four_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    committed_rows: list[object],
) -> None:
    _, inv_id, sale_id = await _first_investor_purchase(client, db_session)
    sale = await _load_sale(db_session, sale_id)
    bonus = await _add_purchase(
        db_session,
        sale,
        legal_basis=PurchaseLegalBasis.GIFT,
        status=PurchaseStatus.ACTIVE,
        units=4,
        source_purchase_id=sale.id,
    )
    expected_bonus = await bonus_parts_of(sale.id, db_session)
    assert expected_bonus >= bonus.units
    await db_session.commit()
    committed_rows.append(bonus)

    async def _html(_prefix: str) -> str:
        return (
            "{{ account_number }}|{{ bonus_parts }}|{{ purchase_type }}|"
            "{{ tranche_number }}|{{ tranche_count }}|"
            "{{ withdrawal_end_date }}|{{ buyer_agreement_accepted_at }}|"
            "{{ buyer_agreement_annex }}"
        )

    async def _assets(_prefix: str, _files: list[str]):
        return lambda _name: ""

    monkeypatch.setattr(
        "app.modules.purchases.agreement_service.get_template_html_cached",
        _html,
    )
    monkeypatch.setattr(
        "app.modules.purchases.agreement_service.make_asset_data_uri_func",
        _assets,
    )

    data = await load_agreement_data(sale_id, inv_id, db_session)
    # A snapshot would be returned as-is; render live.
    data.purchase.agreement_html = None
    try:
        rendered = await render_agreement_html(data, db_session)
    except jinja2.UndefinedError as exc:
        pytest.fail(f"render context lacks a document field: {exc}")

    account, bonus_parts, purchase_type, number, count, end, accepted, annex = (
        rendered.split("|")
    )
    assert end == format_document_date(
        sale.created_at + timedelta(days=14), data.template.language
    )
    assert accepted == "" and annex == ""  # no acceptance recorded
    assert account == str(inv_id).split("-")[0].upper()
    assert int(bonus_parts) == expected_bonus
    assert purchase_type == "sale"
    assert (int(number), int(count)) == (0, 0)


@pytest.mark.asyncio
async def test_resolve_account_number_is_unique_among_users(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, inv_id, _ = await _first_investor_purchase(client, db_session)
    number = await resolve_account_number(inv_id, db_session)
    assert number == inv_id.hex[: len(number)].upper()
    assert len(number) >= 8


# ---------------------------------------------------------------------------
# 3: bonus parts of a purchase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bonus_parts_sum_only_active_bonus_rows_of_this_purchase(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, sale_id = await _first_investor_purchase(client, db_session)
    sale = await _load_sale(db_session, sale_id)
    before = await bonus_parts_of(sale.id, db_session)

    await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.GIFT,
        status=PurchaseStatus.ACTIVE, units=3, source_purchase_id=sale.id,
    )
    await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.GIFT,
        status=PurchaseStatus.ACTIVE, units=2, source_purchase_id=sale.id,
    )
    # Does not count: pending, cancelled, reversed, and no source.
    for status in (
        PurchaseStatus.PENDING_ACCEPTANCE,
        PurchaseStatus.CANCELLED,
        PurchaseStatus.REVERSED,
    ):
        await _add_purchase(
            db_session, sale, legal_basis=PurchaseLegalBasis.GIFT,
            status=status, units=100, source_purchase_id=sale.id,
        )
    await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.GIFT,
        status=PurchaseStatus.ACTIVE, units=100,
    )
    # Another sale's bonus does not count either.
    other_sale = await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.SALE,
        status=PurchaseStatus.ACTIVE, units=1, paid_cents=10_000,
    )
    await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.GIFT,
        status=PurchaseStatus.ACTIVE, units=100,
        source_purchase_id=other_sale.id,
    )

    assert await bonus_parts_of(sale.id, db_session) == before + 5
    assert await bonus_parts_of(other_sale.id, db_session) == 100


@pytest.mark.asyncio
async def test_bonus_parts_are_zero_for_a_purchase_without_bonus_rows(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, sale_id = await _first_investor_purchase(client, db_session)
    sale = await _load_sale(db_session, sale_id)
    lone = await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.SALE,
        status=PurchaseStatus.ACTIVE, units=1, paid_cents=10_000,
    )
    assert await bonus_parts_of(lone.id, db_session) == 0


# ---------------------------------------------------------------------------
# 4: the purchase type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purchase_type_tells_sale_instalment_gift_and_bonus_apart(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, sale_id = await _first_investor_purchase(client, db_session)
    sale = await _load_sale(db_session, sale_id)
    assert await purchase_type_of(sale, db_session) == "sale"

    tranche = await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.INSTALLMENT_TRANCHE,
        status=PurchaseStatus.ACTIVE, units=1, paid_cents=10_000,
    )
    assert await purchase_type_of(tranche, db_session) == "instalment"

    sourced = await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.GIFT,
        status=PurchaseStatus.ACTIVE, units=1, source_purchase_id=sale.id,
    )
    assert await purchase_type_of(sourced, db_session) == "bonus"

    pending = await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.GIFT,
        status=PurchaseStatus.PENDING_ACCEPTANCE, units=1,
    )
    assert await purchase_type_of(pending, db_session) == "gift"

    # An accepted staff gift wrote gift:grant:company:<id> to the ledger;
    # the instalment completion bonus (no source, no such reason) is a bonus.
    accepted = await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.GIFT,
        status=PurchaseStatus.ACTIVE, units=1,
    )
    completion = await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.GIFT,
        status=PurchaseStatus.ACTIVE, units=1,
    )
    await record_active_ledger(
        db_session,
        user_id=sale.investor_id,
        amount_cents=0,
        status=LedgerStatus.CONFIRMED,
        reason=f"gift:grant:company:{accepted.id}",
    )
    assert await purchase_type_of(accepted, db_session) == "gift"
    assert await purchase_type_of(completion, db_session) == "bonus"


# ---------------------------------------------------------------------------
# 5: tranche number and count
# ---------------------------------------------------------------------------


async def _plan_with_tranches(
    db_session: AsyncSession, sale: Purchase, count: int
) -> tuple[InstallmentPlan, list[InstallmentTranche]]:
    template = (
        await db_session.execute(select(ProductInstallment).limit(1))
    ).scalar_one_or_none()
    assert template is not None, "storefront seed must run before tests"
    product = (
        await db_session.execute(
            select(Product).where(Product.id == template.product_id)
        )
    ).scalar_one()
    plan = InstallmentPlan(
        investor_id=sale.investor_id,
        product_id=product.id,
        product_installment_id=template.id,
        company_id=product.company_id,
        plan_config_snapshot={"tranches": [], "bonus_units": 0},
        total_price_cents=10_000 * count,
        total_units=count,
        price_per_unit_cents=10_000,
        status=InstallmentPlanStatus.ACTIVE,
    )
    db_session.add(plan)
    await db_session.flush()
    tranches = [
        InstallmentTranche(
            plan_id=plan.id,
            number=n,
            due_date=date.today(),
            amount_cents=10_000,
            units_unlocked=1,
            status=InstallmentTrancheStatus.SCHEDULED,
        )
        for n in range(1, count + 1)
    ]
    db_session.add_all(tranches)
    await db_session.flush()
    return plan, tranches


@pytest.mark.asyncio
async def test_tranche_position_is_the_paid_tranche_number_of_the_plans_count(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, sale_id = await _first_investor_purchase(client, db_session)
    sale = await _load_sale(db_session, sale_id)
    assert await tranche_position(sale.id, db_session) == (0, 0)

    _, tranches = await _plan_with_tranches(db_session, sale, 6)
    paid = await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.INSTALLMENT_TRANCHE,
        status=PurchaseStatus.ACTIVE, units=1, paid_cents=10_000,
    )
    tranches[2].purchase_id = paid.id
    tranches[2].status = InstallmentTrancheStatus.PAID
    tranches[2].paid_at = datetime.now(UTC)
    await db_session.flush()

    assert await tranche_position(paid.id, db_session) == (3, 6)
    # A tranche not yet paid has no purchase, so the sale stays (0, 0).
    assert await tranche_position(sale.id, db_session) == (0, 0)


# ---------------------------------------------------------------------------
# 6: the ownership history rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ownership_history_rows_carry_type_and_instalment_month(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    committed_rows: list[object],
) -> None:
    company, inv_id, sale_id = await _first_investor_purchase(client, db_session)
    sale = await _load_sale(db_session, sale_id)
    plan, tranches = await _plan_with_tranches(db_session, sale, 4)
    paid = await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.INSTALLMENT_TRANCHE,
        status=PurchaseStatus.ACTIVE, units=1, paid_cents=10_000,
    )
    tranches[1].purchase_id = paid.id
    bonus = await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.GIFT,
        status=PurchaseStatus.ACTIVE, units=2, source_purchase_id=sale.id,
    )
    await db_session.commit()
    # Tranches first: they point at the paid purchase.
    committed_rows.extend([*tranches, plan, paid, bonus])

    data = await load_ownership_data(
        company_id=UUID(company["id"]), user_id=inv_id, session=db_session
    )
    by_id = {item.id: item for item in data.purchases}
    assert by_id[sale_id].purchase_type == "sale"
    assert by_id[paid.id].purchase_type == "instalment"
    assert (by_id[paid.id].tranche_number, by_id[paid.id].tranche_count) == (2, 4)
    kinds = sorted(item.purchase_type for item in data.purchases)
    assert kinds.count("bonus") >= 1


# ---------------------------------------------------------------------------
# 7: dates in the document's language, the cancelled gift
# ---------------------------------------------------------------------------


def test_russian_documents_print_russian_month_names() -> None:
    moment = datetime(2026, 10, 23, 14, 5, tzinfo=UTC)
    assert format_document_date(moment, "ru") == "23 октября 2026 г."
    assert format_document_date(moment, "en") == "October 23, 2026"
    assert format_document_date(moment, "de") == "October 23, 2026"
    assert format_document_datetime(moment, "ru") == (
        "23 октября 2026 г., 14:05 UTC"
    )
    assert format_document_datetime(moment, "en") == (
        "October 23, 2026, 14:05 UTC"
    )


def test_every_russian_month_has_its_genitive_name() -> None:
    names = [
        format_document_date(datetime(2026, m, 1, tzinfo=UTC), "ru")
        for m in range(1, 13)
    ]
    assert [n.split()[1] for n in names] == [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]


@pytest.mark.asyncio
async def test_a_cancelled_staff_gift_is_still_a_gift(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, sale_id = await _first_investor_purchase(client, db_session)
    sale = await _load_sale(db_session, sale_id)
    cancelled = await _add_purchase(
        db_session, sale, legal_basis=PurchaseLegalBasis.GIFT,
        status=PurchaseStatus.CANCELLED, units=1,
    )
    assert await purchase_type_of(cancelled, db_session) == "gift"


# ---------------------------------------------------------------------------
# 8: the acceptance time and the Annex
# ---------------------------------------------------------------------------

_BA_FILE = (
    b'<!DOCTYPE html><html><head><title>Buyer Agreement</title></head><body>'
    b'<article class="legal" lang="en"><h1>Buyer Agreement</h1>'
    b'<p class="edition">Updated 23 October 2026</p>'
    b'<h2 id="ba-h1">1. Subject</h2><p>1.1. The Company owns the IP.</p>'
    b'</article></body></html>'
)


def test_annex_is_the_article_without_its_title_and_edition() -> None:
    html = str(annex_html_from_file(_BA_FILE))
    assert "<h3" in html and "1. Subject" in html
    assert "1.1. The Company owns the IP." in html
    assert "<h1" not in html and "Updated 23 October" not in html
    assert annex_html_from_file(b"<html>no article</html>") is None


def test_annex_text_needs_the_files_hash_to_equal_the_accepted_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "buyer_agreement.html").write_bytes(_BA_FILE)
    monkeypatch.setattr(buyer_agreement_annex, "LEGAL_DIRS", (tmp_path,))
    accepted = Document(
        type="buyer_agreement", version=1, language="en",
        title="Buyer Agreement",
        content_hash=hashlib.sha256(_BA_FILE).hexdigest(),
    )
    assert "1.1. The Company owns the IP." in str(annex_for_document(accepted))
    # The accepted version was replaced by another file: no text is shown.
    replaced = Document(
        type="buyer_agreement", version=1, language="en",
        title="Buyer Agreement", content_hash="0" * 64,
    )
    assert annex_for_document(replaced) is None


@pytest.mark.asyncio
async def test_agreement_prints_the_acceptance_time_and_the_accepted_text(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, inv_id, sale_id = await _first_investor_purchase(client, db_session)
    sale = await _load_sale(db_session, sale_id)
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "buyer_agreement.html").write_bytes(_BA_FILE)
    monkeypatch.setattr(buyer_agreement_annex, "LEGAL_DIRS", (tmp_path,))
    document = Document(
        type="buyer_agreement", version=9001, language="en",
        title="Buyer Agreement",
        content_hash=hashlib.sha256(_BA_FILE).hexdigest(),
        status=DocumentStatus.ACTIVE, created_by=inv_id,
    )
    db_session.add(document)
    await db_session.flush()
    signed_at = sale.created_at - timedelta(hours=1)
    db_session.add(DocumentSigning(
        id=uuid4(), user_id=inv_id, document_id=document.id,
        signed_at=signed_at, ip_address="127.0.0.1", user_agent="pytest",
    ))
    await db_session.commit()

    async def _html(_prefix: str) -> str:
        return "{{ buyer_agreement_accepted_at }}|{{ buyer_agreement_annex }}"

    async def _assets(_prefix: str, _files: list[str]):
        return lambda _name: ""

    monkeypatch.setattr(
        "app.modules.purchases.agreement_service.get_template_html_cached",
        _html,
    )
    monkeypatch.setattr(
        "app.modules.purchases.agreement_service.make_asset_data_uri_func",
        _assets,
    )
    data = await load_agreement_data(sale_id, inv_id, db_session)
    data.purchase.agreement_html = None
    rendered = await render_agreement_html(data, db_session)
    accepted, annex = rendered.split("|", 1)
    assert accepted == format_document_datetime(
        signed_at, data.template.language
    )
    assert "1.1. The Company owns the IP." in annex
