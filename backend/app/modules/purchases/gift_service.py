# =============================================================================
# AIVIS.ONE Backend -- Gift Service
# =============================================================================
#
# FLOW:
#   1. Staff grants gift parts to a user who passed KYC: grant_gift() stores
#      a Purchase in PENDING_ACCEPTANCE. It credits NOTHING: no ledger entry,
#      no transaction-log row (the portfolio figures count ACTIVE
#      purchases only). A staff gift is given from the company's reserve,
#      so it never uses the pool on sale (pools/service.get_pool_consumed).
#   2. The recipient sees it in list_pending_gifts() and accepts it:
#      accept_gift() re-checks the recipient's KYC and hands the row to
#      engine.credit_pending_gift(), which writes the ledger entries through
#      the same helpers a bonus gift uses and flips the row to ACTIVE.
#   3. Until it is accepted, staff may cancel it: cancel_gift() closes the
#      row (status cancelled) with no ledger entry and no credit.
#
# The gift certificate snapshot is taken at the grant (the same template
# resolution a bonus gift gets), so the recipient can read the certificate
# before accepting.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
# =============================================================================

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.companies.models import CompanyProfile
from app.modules.pools.service import get_active_pool
from app.modules.products.constants import ProductStatus
from app.modules.products.models import Product
from app.modules.purchases import engine
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.purchases.service import _load_company
from app.modules.users.models import KYCStatus, User, UserRole

logger = structlog.get_logger()


async def grant_gift(
    *,
    staff: User,
    user_id: UUID,
    product_id: UUID,
    units: int,
    session: AsyncSession,
) -> Purchase:
    """Store a gift for `user_id` that waits for the recipient's acceptance.

    Raises:
        NotFoundError: user or product not found.
        BadRequestError: the recipient is not an active investor who passed
            KYC (codes gift_recipient_not_investor / gift_recipient_not_kyc);
            the product, the company or the pool is not active (codes
            product_not_available / company_not_active / the pool's own).
    """
    recipient = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if recipient is None:
        raise NotFoundError("User not found")
    if recipient.role != UserRole.INVESTOR or not recipient.is_active:
        raise BadRequestError(
            "A gift can be granted to an active investor account only",
            code="gift_recipient_not_investor",
        )
    if recipient.kyc_status != KYCStatus.APPROVED:
        raise BadRequestError(
            "The recipient must pass identity verification before a gift "
            "can be granted",
            code="gift_recipient_not_kyc",
        )

    product = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if product is None:
        raise NotFoundError("Product not found")
    if product.status != ProductStatus.ACTIVE:
        raise BadRequestError(
            f"Product is not available (status={product.status})",
            code="product_not_available",
        )
    await _load_company(product.company_id, session)
    await get_active_pool(product.company_id, session)

    template_id = await engine._snapshot_template_id(
        session,
        company_id=product.company_id,
        legal_basis=PurchaseLegalBasis.GIFT,
        language=recipient.language or "en",
        actor_id=staff.id,
    )

    purchase = Purchase(
        investor_id=recipient.id,
        product_id=product.id,
        company_id=product.company_id,
        legal_basis=PurchaseLegalBasis.GIFT,
        units=units,
        paid_cents=0,
        price_per_unit_cents=product.price_per_unit_cents,
        status=PurchaseStatus.PENDING_ACCEPTANCE,
        purchase_agreement_template_id=template_id,
    )
    session.add(purchase)
    await session.flush()

    await record_audit(
        session=session,
        event="purchase.gift_granted",
        actor_id=staff.id,
        actor_type="staff",
        target_type="purchase",
        target_id=purchase.id,
        data={
            "recipient_id": str(recipient.id),
            "product_id": str(product.id),
            "company_id": str(product.company_id),
            "units": units,
        },
    )
    logger.info(
        "gift_granted",
        purchase_id=str(purchase.id),
        recipient_id=str(recipient.id),
        units=units,
    )
    return purchase


async def list_pending_gifts(
    investor_id: UUID, session: AsyncSession
) -> list[Purchase]:
    """The caller's gifts that wait for acceptance, oldest first."""
    stmt = (
        select(Purchase)
        .where(
            Purchase.investor_id == investor_id,
            Purchase.legal_basis == PurchaseLegalBasis.GIFT,
            Purchase.status == PurchaseStatus.PENDING_ACCEPTANCE,
        )
        .order_by(Purchase.created_at.asc(), Purchase.id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def accept_gift(
    purchase_id: UUID, investor: User, session: AsyncSession
) -> Purchase:
    """The recipient accepts a pending gift; the parts are credited.

    Raises:
        NotFoundError: no such gift for this caller (also for someone
            else's gift, so ids are not probeable).
        ConflictError: the gift is not waiting for acceptance
            (code gift_not_pending) -- accepted already, or cancelled.
        BadRequestError: the recipient's identity verification is no longer
            approved (code kyc_required).
    """
    if investor.kyc_status != KYCStatus.APPROVED:
        raise BadRequestError(
            "Identity verification is required to accept a gift",
            code="kyc_required",
        )
    purchase = (
        await session.execute(
            select(Purchase)
            .where(
                Purchase.id == purchase_id,
                Purchase.investor_id == investor.id,
                Purchase.legal_basis == PurchaseLegalBasis.GIFT,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if purchase is None:
        raise NotFoundError("Gift not found")
    if purchase.status != PurchaseStatus.PENDING_ACCEPTANCE:
        raise ConflictError(
            "This gift is not waiting for acceptance",
            code="gift_not_pending",
        )

    company = (
        await session.execute(
            select(CompanyProfile).where(CompanyProfile.id == purchase.company_id)
        )
    ).scalar_one()

    await engine.credit_pending_gift(
        session, purchase, company_user_id=company.user_id
    )
    logger.info(
        "gift_accepted",
        purchase_id=str(purchase.id),
        investor_id=str(investor.id),
    )
    return purchase


async def cancel_gift(
    purchase_id: UUID, staff: User, session: AsyncSession
) -> Purchase:
    """Staff closes a staff gift that the recipient has not accepted.

    The row goes to status cancelled (a value the migration that adds
    pending_acceptance allows). Nothing was credited at the grant, so no ledger entry is
    written and nothing is returned; an audit entry records the act.

    Raises:
        NotFoundError: no such gift.
        ConflictError: the gift is not waiting for acceptance
            (code gift_not_pending).
    """
    purchase = (
        await session.execute(
            select(Purchase)
            .where(
                Purchase.id == purchase_id,
                Purchase.legal_basis == PurchaseLegalBasis.GIFT,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if purchase is None:
        raise NotFoundError("Gift not found")
    if purchase.status != PurchaseStatus.PENDING_ACCEPTANCE:
        raise ConflictError(
            "This gift is not waiting for acceptance",
            code="gift_not_pending",
        )

    purchase.status = PurchaseStatus.CANCELLED
    await session.flush()

    await record_audit(
        session=session,
        event="purchase.gift_cancelled",
        actor_id=staff.id,
        actor_type="staff",
        target_type="purchase",
        target_id=purchase.id,
        data={
            "recipient_id": str(purchase.investor_id),
            "product_id": str(purchase.product_id),
            "company_id": str(purchase.company_id),
            "units": purchase.units,
        },
    )
    logger.info(
        "gift_cancelled",
        purchase_id=str(purchase.id),
        staff_id=str(staff.id),
    )
    return purchase
