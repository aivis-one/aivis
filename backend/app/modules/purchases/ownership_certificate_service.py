# =============================================================================
# CBSHOME Backend -- Ownership Certificate Service (Refactor 2 iter 2.4,
#                                                     R2 §5.3-5.4)
# =============================================================================
#
# RESPONSIBILITIES:
#   load_ownership_data() -- live aggregate of all of an investor's
#                            Purchases for one company
#   render_ownership_html() -- Jinja2 render against the company's
#                              ownership_certificate template
#   generate_ownership_pdf() -- HTML -> PDF via xhtml2pdf
#   send_ownership_email()   -- email the PDF via core/email
#
# DIFFERENCE FROM AGREEMENT (R2 §5.3):
#   The ownership certificate has NO per-Purchase snapshot. It reflects
#   the investor's *current* portfolio for one company, so each request
#   resolves the template fresh via find_active_template(). HTML body
#   still rides the 5-min Redis cache (R2 §4.10), so the cost of
#   per-request resolution is one DB SELECT + one Redis GET in steady
#   state -- the MinIO read only fires on cache miss.
#
# 500 ON MISSING TEMPLATE (R2 §5.3):
#   If find_active_template returns None across all 4 fallback stages
#   (per-company-locale, per-company-en, platform-locale, platform-en)
#   we raise TemplateMissingError -> 500. Platform defaults are seeded
#   at install time, so this only fires on a broken stack.
#
# AGGREGATE SCOPE (R2 §5.3):
#   All Purchases for (investor_id, company_id) with status != reversed.
#   sale_units = SUM(legal_basis IN sale + installment_tranche)
#   gift_units = SUM(legal_basis = gift)
#   total_units = sale_units + gift_units
#
#   Rationale for installment_tranche rolled into sale_units: from a
#   legal-document standpoint both are "paid for in money" (gift is
#   the only no-cash branch). The bootstrap ownership_certificate
#   templates expect two counters; keeping the two-bucket shape avoids
#   re-seeding all 4 language variants this iteration. The detailed
#   per-Purchase array is still surfaced as `purchases[]` for templates
#   that want to itemise.
#
# ACCESS:
#   Available to any authenticated user querying their own portfolio.
#   Avatar mode works automatically (get_current_user returns target user).
#
# COMMIT RULE (P-01):
#   Service never commits. Read-only queries only.
# =============================================================================

import io
from dataclasses import dataclass
from datetime import datetime, UTC
from uuid import UUID

import structlog
from jinja2 import Environment, StrictUndefined
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email
from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.companies.constants import DocumentTemplateKind
from app.modules.companies.models import CompanyProfile
from app.modules.companies.service import (
    find_active_template,
    get_template_html_cached,
    make_asset_data_uri_func,
)
from app.modules.purchases.agreement_service import (
    TemplateMissingError,
    _extract_investor_email,
    _extract_investor_name,
    _format_cents,
)
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.users.models import User

logger = structlog.get_logger()


@dataclass
class OwnershipPurchaseItem:
    """Single row in the ownership certificate's purchases[] array.

    Mirrors the data the template needs without exposing internal ORM
    fields. legal_basis / paid_cents stay raw so the template can do
    its own currency formatting if it wants to.
    """

    id: UUID
    legal_basis: str
    units: int
    paid_cents: int
    price_per_unit_cents: int
    purchase_date: datetime


@dataclass
class OwnershipData:
    """All data needed to render an ownership certificate."""

    investor_user: User
    investor_name: str
    investor_email: str | None
    company: CompanyProfile
    total_units: int
    sale_units: int
    gift_units: int
    total_paid_cents: int
    current_value_cents: int
    as_of_date: datetime
    purchases: list[OwnershipPurchaseItem]


async def load_ownership_data(
    company_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> OwnershipData:
    """Load all of the user's Purchases for one company and build the
    aggregate.

    Raises:
        NotFoundError: Company doesn't exist, OR user has zero active
            Purchases for it. We surface 404 (not "empty certificate")
            because rendering an ownership certificate for someone who
            owns nothing in this company is meaningless and would
            confuse the recipient.
    """
    # Load company first -- separate from the aggregate so a missing
    # company surfaces as 404 cleanly.
    company_stmt = select(CompanyProfile).where(CompanyProfile.id == company_id)
    company = (await session.execute(company_stmt)).scalar_one_or_none()
    if company is None:
        raise NotFoundError("Company not found")

    # Load investor user (need profile/credentials for name + email).
    user_stmt = select(User).where(User.id == user_id)
    investor = (await session.execute(user_stmt)).scalar_one_or_none()
    if investor is None:
        raise NotFoundError("User not found")

    # Load all active Purchases for (investor, company).
    purchases_stmt = (
        select(Purchase)
        .where(
            Purchase.investor_id == user_id,
            Purchase.company_id == company_id,
            Purchase.status == PurchaseStatus.ACTIVE,
        )
        .order_by(Purchase.created_at.asc())
    )
    purchases_result = await session.execute(purchases_stmt)
    purchases = list(purchases_result.scalars().all())

    if not purchases:
        raise NotFoundError("No active purchases for this company")

    sale_units = 0
    gift_units = 0
    total_paid_cents = 0
    items: list[OwnershipPurchaseItem] = []

    # SALE + INSTALLMENT_TRANCHE roll into sale_units (both money-backed).
    # See module docstring for the rationale + the iter 2.4 design call.
    paid_bases = {
        PurchaseLegalBasis.SALE,
        PurchaseLegalBasis.INSTALLMENT_TRANCHE,
    }

    for p in purchases:
        if p.legal_basis in paid_bases:
            sale_units += p.units
        elif p.legal_basis == PurchaseLegalBasis.GIFT:
            gift_units += p.units
        # Defensive: an unknown future legal_basis is folded into total
        # via items[] but not double-counted; sale/gift stay accurate.

        total_paid_cents += p.paid_cents

        items.append(
            OwnershipPurchaseItem(
                id=p.id,
                legal_basis=p.legal_basis,
                units=p.units,
                paid_cents=p.paid_cents,
                price_per_unit_cents=p.price_per_unit_cents,
                purchase_date=p.created_at,
            )
        )

    total_units = sale_units + gift_units
    current_value_cents = total_units * company.price_per_unit_cents

    return OwnershipData(
        investor_user=investor,
        investor_name=_extract_investor_name(investor),
        investor_email=_extract_investor_email(investor),
        company=company,
        total_units=total_units,
        sale_units=sale_units,
        gift_units=gift_units,
        total_paid_cents=total_paid_cents,
        current_value_cents=current_value_cents,
        as_of_date=datetime.now(UTC),
        purchases=items,
    )


async def render_ownership_html(
    data: OwnershipData,
    session: AsyncSession,
) -> str:
    """Render the ownership certificate HTML.

    Per R2 §5.3 there is no per-Purchase snapshot here; the template is
    resolved live via the 4-stage fallback in find_active_template.
    A genuine miss across all 4 stages raises TemplateMissingError (500).

    Args:
        data: Pre-loaded OwnershipData (use load_ownership_data).
        session: Active DB session, forwarded to find_active_template.

    Returns:
        Rendered HTML string.

    Raises:
        TemplateMissingError: 4-stage fallback returned nothing.
        BadRequestError: A referenced asset isn't in the template's
            declared asset_files (raised by asset_data_uri).
        StorageError / StorageNotFoundError: MinIO failures bubble up
            to the caller as 500.
        jinja2.UndefinedError: StrictUndefined triggered by a missing
            placeholder in the template (treated as 500).
    """
    language = data.investor_user.language or "en"

    template = await find_active_template(
        company_id=data.company.id,
        kind=DocumentTemplateKind.OWNERSHIP_CERTIFICATE,
        language=language,
        session=session,
    )

    if template is None:
        # All four fallback stages missed. Platform defaults should
        # cover this -- a real miss means seed or MinIO is broken.
        logger.error(
            "ownership_template_missing",
            company_id=str(data.company.id),
            language=language,
        )
        raise TemplateMissingError()

    html_body = await get_template_html_cached(template.storage_prefix)

    asset_data_uri = await make_asset_data_uri_func(
        template.storage_prefix,
        template.asset_files,
    )

    # SEC-NEW-01 closure (R2 §5.4): autoescape + StrictUndefined,
    # identical hardening as the per-Purchase agreement renderer.
    env = Environment(
        autoescape=True,
        undefined=StrictUndefined,
    )
    env.globals["asset_data_uri"] = asset_data_uri

    template_obj = env.from_string(html_body)

    # Build the template context. Numeric fields are surfaced both raw
    # (for templates that want their own formatting) and pre-formatted
    # via _format_cents so simple templates don't need a custom filter.
    # The per-item `date` key (not `purchase_date`) matches the bootstrap
    # ownership_certificate templates which iterate {% for p in purchases %}
    # and render {{ p.date }} (R2 §4.4).
    purchases_for_template = [
        {
            "id": str(item.id),
            "legal_basis": item.legal_basis,
            "units": item.units,
            "paid_cents": item.paid_cents,
            "paid_display": _format_cents(item.paid_cents),
            "price_per_unit_cents": item.price_per_unit_cents,
            "price_per_unit_display": _format_cents(item.price_per_unit_cents),
            "date": item.purchase_date.strftime("%B %d, %Y"),
        }
        for item in data.purchases
    ]

    context = {
        "investor_name": data.investor_name,
        "company_name": data.company.name,
        "company_logo_url": data.company.logo_url,
        "total_units": data.total_units,
        "sale_units": data.sale_units,
        "gift_units": data.gift_units,
        "total_paid_cents": data.total_paid_cents,
        "total_paid_display": _format_cents(data.total_paid_cents),
        "current_value_cents": data.current_value_cents,
        "current_value_display": _format_cents(data.current_value_cents),
        "as_of_date": data.as_of_date.strftime("%B %d, %Y"),
        "purchases": purchases_for_template,
    }

    return template_obj.render(**context)


def generate_ownership_pdf(html: str) -> bytes:
    """Convert ownership certificate HTML to PDF bytes via xhtml2pdf.

    Same engine as the per-Purchase agreement; logged failures surface
    as BadRequestError (400) because a render-output the converter
    can't handle is a template authoring bug, not a system outage.
    """
    from xhtml2pdf import pisa

    buffer = io.BytesIO()
    result = pisa.CreatePDF(io.StringIO(html), dest=buffer)

    if result.err:
        logger.error("ownership_pdf_generation_failed", errors=result.err)
        raise BadRequestError("Failed to generate ownership certificate PDF")

    return buffer.getvalue()


async def send_ownership_email(
    data: OwnershipData,
    pdf_bytes: bytes,
) -> bool:
    """Send the ownership certificate PDF to the investor's email.

    Uses core/email.send_email() with the full SMTP/Mailgun routing
    logic. Raises BadRequestError if the investor has no email.
    """
    if not data.investor_email:
        raise BadRequestError("Investor has no email address on file")

    issued = data.as_of_date.strftime("%Y%m%d")
    filename = f"ownership_{data.company.id}_{issued}.pdf"

    success = await send_email(
        recipient=data.investor_email,
        subject=f"Ownership Certificate -- {data.company.name}",
        body=(
            f"Dear {data.investor_name},\n\n"
            f"Please find your ownership certificate for "
            f"{data.company.name} attached.\n\n"
            f"Total units owned: {data.total_units}\n"
            f"Current value: {_format_cents(data.current_value_cents)}\n"
            f"As of: {data.as_of_date.strftime('%B %d, %Y')}\n\n"
            f"Best regards,\n"
            f"CBSHOME Platform"
        ),
        attachment=(filename, pdf_bytes, "application/pdf"),
    )

    if success:
        logger.info(
            "ownership_email_sent",
            company_id=str(data.company.id),
            investor_id=str(data.investor_user.id),
        )
    else:
        logger.error(
            "ownership_email_failed",
            company_id=str(data.company.id),
            investor_id=str(data.investor_user.id),
        )

    return success
