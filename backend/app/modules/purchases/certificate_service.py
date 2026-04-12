# =============================================================================
# CBSHOME Backend -- Certificate Service (Sprint 9.2)
# =============================================================================
#
# RESPONSIBILITIES:
#   load_certificate_data() -- load and verify purchase + related entities
#   render_certificate_html() -- Jinja2 template rendering
#   generate_certificate_pdf() -- HTML -> PDF via xhtml2pdf
#   send_certificate_email()  -- send PDF attachment via core/email
#
# ACCESS:
#   Certificate is available to the purchase owner only.
#   Avatar mode works automatically (get_current_user returns target user).
#
# TEMPLATE:
#   app/modules/purchases/templates/certificate.html (Jinja2).
#   Placeholder graphics for seal, signature, background.
#
# COMMIT RULE (P-01):
#   Service never commits. Read-only queries only.
# =============================================================================

import io
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from uuid import UUID

import structlog
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email
from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.companies.models import CompanyProfile
from app.modules.products.models import Product
from app.modules.purchases.constants import PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.users.models import User

logger = structlog.get_logger()

# Template directory (relative to this file).
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)

# Legal basis display names.
_LEGAL_BASIS_DISPLAY = {
    "sale": "Purchase Agreement",
    "gift": "Gift Certificate",
    "installment_tranche": "Installment Certificate",
}


@dataclass
class CertificateData:
    """All data needed to render a certificate."""

    purchase: Purchase
    investor: User
    company: CompanyProfile
    product: Product


async def load_certificate_data(
    purchase_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> CertificateData:
    """Load purchase and related entities, verify ownership.

    Raises:
        NotFoundError: Purchase not found or not owned by user.
    """
    # Load purchase.
    stmt = select(Purchase).where(Purchase.id == purchase_id)
    result = await session.execute(stmt)
    purchase = result.scalar_one_or_none()

    if purchase is None:
        raise NotFoundError("Purchase not found")

    if purchase.investor_id != user_id:
        raise NotFoundError("Purchase not found")

    if purchase.status != PurchaseStatus.ACTIVE:
        raise NotFoundError("Purchase not found")

    # Load investor user.
    inv_stmt = select(User).where(User.id == purchase.investor_id)
    inv_result = await session.execute(inv_stmt)
    investor = inv_result.scalar_one_or_none()

    if investor is None:
        raise NotFoundError("Investor not found")

    # Load company.
    comp_stmt = select(CompanyProfile).where(
        CompanyProfile.id == purchase.company_id
    )
    comp_result = await session.execute(comp_stmt)
    company = comp_result.scalar_one_or_none()

    if company is None:
        raise NotFoundError("Company not found")

    # Load product.
    prod_stmt = select(Product).where(Product.id == purchase.product_id)
    prod_result = await session.execute(prod_stmt)
    product = prod_result.scalar_one_or_none()

    if product is None:
        raise NotFoundError("Product not found")

    return CertificateData(
        purchase=purchase,
        investor=investor,
        company=company,
        product=product,
    )


def _extract_investor_name(user: User) -> str:
    """Extract display name from User.profile JSONB."""
    if user.profile:
        first = user.profile.get("first_name", "")
        last = user.profile.get("last_name", "")
        full = f"{first} {last}".strip()
        if full:
            return full

    # Fallback to email prefix.
    email_creds = (user.credentials or {}).get("email", {})
    email = email_creds.get("email", "")
    if email and "@" in email:
        return email.split("@")[0]

    return "Investor"


def _format_cents(cents: int) -> str:
    """Format cents as dollar string: 150000 -> '1,500.00'."""
    dollars = cents / 100
    return f"{dollars:,.2f}"


def _short_id(purchase_id: UUID) -> str:
    """Short certificate number from purchase UUID: first 8 chars uppercase."""
    return str(purchase_id).split("-")[0].upper()


def render_certificate_html(data: CertificateData) -> str:
    """Render certificate HTML from template and purchase data."""
    template = _jinja_env.get_template("certificate.html")

    investor_name = _extract_investor_name(data.investor)
    legal_basis = data.purchase.legal_basis
    now = datetime.now(UTC)

    context = {
        "investor_name": investor_name,
        "company_name": data.company.name,
        "company_logo_url": data.company.logo_url,
        "product_name": data.product.name,
        "units": data.purchase.units,
        "price_per_unit_display": _format_cents(
            data.purchase.price_per_unit_cents
        ),
        "paid_display": _format_cents(data.purchase.paid_cents),
        "legal_basis": legal_basis,
        "legal_basis_display": _LEGAL_BASIS_DISPLAY.get(
            legal_basis, legal_basis.replace("_", " ").title()
        ),
        "purchase_date": data.purchase.created_at.strftime("%B %d, %Y"),
        "issue_date": now.strftime("%B %d, %Y"),
        "certificate_number": _short_id(data.purchase.id),
    }

    return template.render(**context)


def generate_certificate_pdf(html: str) -> bytes:
    """Convert certificate HTML to PDF via xhtml2pdf.

    Returns PDF bytes.
    """
    from xhtml2pdf import pisa

    buffer = io.BytesIO()
    result = pisa.CreatePDF(io.StringIO(html), dest=buffer)

    if result.err:
        logger.error("certificate_pdf_generation_failed", errors=result.err)
        raise BadRequestError("Failed to generate certificate PDF")

    return buffer.getvalue()


async def send_certificate_email(
    data: CertificateData,
    pdf_bytes: bytes,
) -> bool:
    """Send certificate PDF to the investor's email.

    Uses core/email.send_email() with full SMTP/Mailgun routing.

    Raises:
        BadRequestError: If investor has no email.
    """
    email_creds = (data.investor.credentials or {}).get("email", {})
    recipient = email_creds.get("email")

    if not recipient:
        raise BadRequestError("Investor has no email address")

    cert_number = _short_id(data.purchase.id)
    filename = f"certificate_{cert_number}.pdf"

    success = await send_email(
        recipient=recipient,
        subject=f"Investment Certificate — {cert_number}",
        body=(
            f"Dear {_extract_investor_name(data.investor)},\n\n"
            f"Please find your investment certificate attached.\n\n"
            f"Certificate: {cert_number}\n"
            f"Company: {data.company.name}\n"
            f"Units: {data.purchase.units}\n\n"
            f"Best regards,\n"
            f"CBSHOME Platform"
        ),
        attachment=(filename, pdf_bytes, "application/pdf"),
    )

    if success:
        logger.info(
            "certificate_email_sent",
            purchase_id=str(data.purchase.id),
            recipient_masked=recipient.split("@")[0][0] + "***@"
            + recipient.split("@")[1]
            if "@" in recipient
            else "***",
        )
    else:
        logger.error(
            "certificate_email_failed",
            purchase_id=str(data.purchase.id),
        )

    return success
