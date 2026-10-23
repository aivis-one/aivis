# =============================================================================
# AIVIS.ONE Backend -- Staff purchases list (read-only)
# =============================================================================
#
# FLOW:
#   GET /api/v1/staff/purchases reads purchases for the staff cabinet's
#   Finance > Purchases screen: paged, newest first, filtered by status,
#   project (company) and buyer. It writes nothing and needs no migration:
#   every column it reads already exists on purchases, users,
#   company_profiles and products.
#
# The pure helpers (filter building, offset, kind) carry no session so a test
# can check them without a database.
#
# KIND (the "type" column of the screen), derived from legal_basis and
# source_purchase_id:
#   sale                          -> paid
#   installment_tranche           -> installment
#   gift with a source purchase   -> bonus (written with a sale or a tranche)
#   gift without a source         -> gift when staff granted it (pending,
#                                    cancelled, or accepted with the ledger
#                                    reason gift:grant:company:<id>); else
#                                    bonus (the instalment completion bonus),
#                                    the rule of agreement_service.purchase_type_of
#
# COMMIT RULE (P-01):
#   Service never commits and never writes.
# =============================================================================

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import CompanyProfile
from app.modules.ledgers.models import ActiveLedger
from app.modules.products.models import Product
from app.modules.purchases.agreement_service import STAFF_GIFT_REASON
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.purchases.schemas import StaffPurchaseItem
from app.modules.users.models import User

KIND_PAID = "paid"
KIND_INSTALLMENT = "installment"
KIND_GIFT = "gift"
KIND_BONUS = "bonus"


def purchase_kind(
    legal_basis: str,
    source_purchase_id: UUID | None,
    status: str,
    staff_granted: bool,
) -> str:
    """The type the staff screen shows; the same rule as
    agreement_service.purchase_type_of, the staff-grant ledger read for
    the whole page at once."""
    if legal_basis == PurchaseLegalBasis.SALE:
        return KIND_PAID
    if legal_basis == PurchaseLegalBasis.INSTALLMENT_TRANCHE:
        return KIND_INSTALLMENT
    if source_purchase_id is not None:
        return KIND_BONUS
    if status in (PurchaseStatus.PENDING_ACCEPTANCE, PurchaseStatus.CANCELLED):
        return KIND_GIFT
    return KIND_GIFT if staff_granted else KIND_BONUS


def page_offset(page: int, per_page: int) -> int:
    """Rows to skip for a 1-based page."""
    return (page - 1) * per_page


def build_purchase_filters(
    *,
    status: str | None = None,
    company_id: UUID | None = None,
    buyer_id: UUID | None = None,
) -> list[ColumnElement[bool]]:
    """The WHERE conditions of the list; an empty filter adds none."""
    conditions: list[ColumnElement[bool]] = []
    if status is not None:
        conditions.append(Purchase.status == status)
    if company_id is not None:
        conditions.append(Purchase.company_id == company_id)
    if buyer_id is not None:
        conditions.append(Purchase.investor_id == buyer_id)
    return conditions


def build_list_statement(
    conditions: list[ColumnElement[bool]],
    *,
    page: int,
    per_page: int,
) -> Select[Any]:
    """The page query: purchases with buyer, project and product, newest first."""
    return (
        select(Purchase, User, CompanyProfile.name, Product.name)
        .join(User, User.id == Purchase.investor_id)
        .join(CompanyProfile, CompanyProfile.id == Purchase.company_id)
        .join(Product, Product.id == Purchase.product_id)
        .where(*conditions)
        .order_by(Purchase.created_at.desc(), Purchase.id.desc())
        .offset(page_offset(page, per_page))
        .limit(per_page)
    )


def buyer_name(profile: dict[str, Any] | None) -> str | None:
    """First and last name from the user's profile JSON, or None."""
    data = profile or {}
    parts = [data.get("first_name"), data.get("last_name")]
    name = " ".join(str(part) for part in parts if part)
    return name or None


async def list_staff_purchases(
    session: AsyncSession,
    *,
    status: str | None = None,
    company_id: UUID | None = None,
    buyer_id: UUID | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[StaffPurchaseItem], int]:
    """One page of purchases and the total that match the filters."""
    conditions = build_purchase_filters(
        status=status, company_id=company_id, buyer_id=buyer_id
    )
    total = (
        await session.execute(
            select(func.count()).select_from(Purchase).where(*conditions)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            build_list_statement(conditions, page=page, per_page=per_page)
        )
    ).all()
    reasons = {
        STAFF_GIFT_REASON.format(purchase_id=purchase.id): purchase.id
        for purchase, _, _, _ in rows
        if purchase.legal_basis == PurchaseLegalBasis.GIFT
        and purchase.source_purchase_id is None
    }
    granted: set[UUID] = set()
    if reasons:
        found = await session.execute(
            select(ActiveLedger.reason).where(ActiveLedger.reason.in_(list(reasons)))
        )
        granted = {reasons[r] for r in found.scalars().all()}
    items = [
        StaffPurchaseItem(
            id=purchase.id,
            created_at=purchase.created_at,
            buyer_id=purchase.investor_id,
            buyer_email=user.email,
            buyer_name=buyer_name(user.profile),
            company_id=purchase.company_id,
            company_name=company_name,
            product_id=purchase.product_id,
            product_name=product_name,
            units=purchase.units,
            paid_cents=purchase.paid_cents,
            kind=purchase_kind(
                purchase.legal_basis,
                purchase.source_purchase_id,
                purchase.status,
                purchase.id in granted,
            ),
            legal_basis=purchase.legal_basis,
            status=purchase.status,
        )
        for purchase, user, company_name, product_name in rows
    ]
    return items, total
