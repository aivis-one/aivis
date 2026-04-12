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
# REVIEW FIXES (Sprint 9.2):
#   - Single JOIN query instead of 4 sequential SELECTs
#   - CertificateData stores investor_name/email, not full User object
#     (avoids holding credentials/password_hash in memory)
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
    """All data needed to render a certificate.

    Stores extracted investor_name/email instead of full User
    to avoid holding credentials (password_hash) in memory.
    """

    purchase: Purchase
    investor_name: str
    investor_email: str | None
    company: CompanyProfile
    product: Product


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
    email_addr = email_creds.get("email", "")
    if email_addr and "@" in email_addr:
        return email_addr.split("@")[0]

    return "Investor"


def _extract_investor_email(user: User) -> str | None:
    """Extract email address from User.credentials JSONB."""
    email_creds = (user.credentials or {}).get("email", {})
    return email_creds.get("email")


async def load_certificate_data(
    purchase_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> CertificateData:
    """Load purchase and related entities in a single JOIN, verify ownership.

    Raises:
        NotFoundError: Purchase not found or not owned by user.
    """
    stmt = (
        select(Purchase, User, CompanyProfile, Product)
        .join(User, Purchase.investor_id == User.id)
        .join(CompanyProfile, Purchase.company_id == CompanyProfile.id)
        .join(Product, Purchase.product_id == Product.id)
        .where(
            Purchase.id == purchase_id,
            Purchase.investor_id == user_id,
            Purchase.status == PurchaseStatus.ACTIVE,
        )
    )

    result = await session.execute(stmt)
    row = result.one_or_none()

    if row is None:
        raise NotFoundError("Purchase not found")

    purchase, investor, company, product = row

    return CertificateData(
        purchase=purchase,
        investor_name=_extract_investor_name(investor),
        investor_email=_extract_investor_email(investor),
        company=company,
        product=product,
    )


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

    legal_basis = data.purchase.legal_basis
    now = datetime.now(UTC)

    context = {
        "investor_name": data.investor_name,
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
    if not data.investor_email:
        raise BadRequestError("Investor has no email address")

    cert_number = _short_id(data.purchase.id)
    filename = f"certificate_{cert_number}.pdf"

    success = await send_email(
        recipient=data.investor_email,
        subject=f"Investment Certificate — {cert_number}",
        body=(
            f"Dear {data.investor_name},\n\n"
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
        )
    else:
        logger.error(
            "certificate_email_failed",
            purchase_id=str(data.purchase.id),
        )

    return success
