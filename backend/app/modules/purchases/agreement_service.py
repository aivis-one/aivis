# =============================================================================
# AIVIS.ONE Backend -- Purchase Agreement Service (Refactor 2 iter 2.4, R2 §5.4)
# =============================================================================
#
# RESPONSIBILITIES:
#   load_agreement_data() -- load + verify purchase + related entities
#   render_agreement_html() -- Jinja2 render from MinIO-stored template
#   generate_agreement_pdf() -- HTML -> PDF via xhtml2pdf
#   send_agreement_email()  -- email the PDF via core/email
#
# REPLACES (Sprint 9.2):
#   purchases/certificate_service.py was a hardcoded global HTML
#   template at purchases/templates/certificate.html with a single
#   _LEGAL_BASIS_DISPLAY mapping for the header. That setup didn't
#   support per-company branding, per-language documents, or template
#   snapshot at purchase time -- all required by R2 §5.
#
# Refactor 2 iter 2.4 (R2 §5.4):
#   - Template is resolved via Purchase.purchase_agreement_template_id
#     (snapshotted at purchase creation, see purchases/engine.py).
#   - HTML body is read from MinIO at
#     <template.storage_prefix>/template.html, through the 5-min Redis
#     cache in companies.service.get_template_html_cached.
#   - Binary assets (logo / signature / stamp) are loaded inline via
#     the Jinja-global asset_data_uri() function built by
#     companies.service.make_asset_data_uri_func.
#   - The Jinja2 Environment is constructed with autoescape=True and
#     undefined=StrictUndefined to close SEC-NEW-01 from iter 2.3.
#     autoescape protects against XSS when investor-supplied fields
#     (investor_name, description, ...) flow into the HTML body;
#     StrictUndefined turns silent placeholder typos into a loud
#     UndefinedError instead of producing a document with literal
#     "{{ certificate_number }}" text where a value was expected.
#
# 500 ON MISSING TEMPLATE (R2 §5.3):
#   If purchase.purchase_agreement_template_id is NULL we raise
#   TemplateMissingError (status 500). In normal production this
#   never fires -- platform defaults are seeded for every
#   (kind, language) pair. A NULL means the seed or MinIO was broken
#   at purchase time, and Staff already has a `purchase.template_missing`
#   audit row to act on.
#
# ACCESS:
#   The agreement is available to the purchase owner only.
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
from app.core.exceptions import BadRequestError, AivisError, NotFoundError
from app.modules.companies.models import CompanyDocumentTemplate, CompanyProfile
from app.modules.companies.service import (
    get_template_html_cached,
    make_asset_data_uri_func,
)
from app.modules.products.models import Product
from app.modules.purchases.constants import PurchaseStatus
from app.modules.purchases.document_utils import (
    extract_investor_email,
    extract_investor_name,
    format_cents,
)
from app.modules.purchases.models import Purchase
from app.modules.users.models import User

logger = structlog.get_logger()


class TemplateMissingError(AivisError):
    """Raised when Purchase.purchase_agreement_template_id is NULL.

    Surfaced as HTTP 500 because in normal production every Purchase has
    a snapshotted template (the platform-default 4-stage fallback in
    find_active_template never genuinely misses). A NULL is a broken-
    infrastructure signal Staff must fix via reconcile, not a 404.
    """

    def __init__(self) -> None:
        super().__init__(
            message="The agreement for this purchase is not configured (system error)",
            code="agreement_template_missing",
            status_code=500,
        )


@dataclass
class AgreementData:
    """All data needed to render a per-Purchase agreement.

    Stores extracted investor_name/email instead of full User to avoid
    holding credentials (password_hash) in memory across the render.
    """

    purchase: Purchase
    investor_name: str
    investor_email: str | None
    company: CompanyProfile
    product: Product
    template: CompanyDocumentTemplate


async def load_agreement_data(
    purchase_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> AgreementData:
    """Load purchase + related entities in a single JOIN, verify ownership.

    Joins on Purchase + User + CompanyProfile + Product + (optional)
    CompanyDocumentTemplate. The template join is a LEFT OUTER JOIN so
    we can distinguish "purchase doesn't exist" (NotFoundError) from
    "purchase exists but template_id is NULL" (TemplateMissingError
    raised by the renderer).

    Raises:
        NotFoundError: Purchase not found, not owned by user, or not
            in ACTIVE status (reversed agreements aren't surfaced).
        TemplateMissingError: Purchase exists but template_id is NULL.
    """
    stmt = (
        select(Purchase, User, CompanyProfile, Product, CompanyDocumentTemplate)
        .join(User, Purchase.investor_id == User.id)
        .join(CompanyProfile, Purchase.company_id == CompanyProfile.id)
        .join(Product, Purchase.product_id == Product.id)
        .outerjoin(
            CompanyDocumentTemplate,
            Purchase.purchase_agreement_template_id == CompanyDocumentTemplate.id,
        )
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

    purchase, investor, company, product, template = row

    if template is None:
        # Purchase.purchase_agreement_template_id was NULL or pointed at
        # a row that has since been deleted (ondelete=SET NULL fired).
        # Either way: no template to render against. Staff sees the
        # broken Purchase in audit (purchase.template_missing).
        logger.error(
            "agreement_render_template_missing",
            purchase_id=str(purchase_id),
            company_id=str(company.id),
        )
        raise TemplateMissingError()

    return AgreementData(
        purchase=purchase,
        investor_name=extract_investor_name(investor),
        investor_email=extract_investor_email(investor),
        company=company,
        product=product,
        template=template,
    )


def _short_id(purchase_id: UUID) -> str:
    """Short certificate number derived from a Purchase UUID.

    Picks the first 8 hex chars of the UUID, uppercased. Stable across
    renders and globally unique enough for human reference.
    """
    return str(purchase_id).split("-")[0].upper()


async def render_agreement_html(
    data: AgreementData,
    session: AsyncSession,
) -> str:
    """Render the per-Purchase agreement HTML.

    Pulls template.html from MinIO via the Redis-cached path, builds
    the asset_data_uri Jinja-global, sets up a hardened Environment
    (autoescape + StrictUndefined), and renders against the per-Purchase
    context.

    Args:
        data: Pre-loaded AgreementData (use load_agreement_data).
        session: Active DB session, only used by upstream helpers.

    Returns:
        Rendered HTML string.

    Raises:
        BadRequestError: A referenced asset isn't in the template's
            declared asset_files (raised by asset_data_uri).
        StorageError / StorageNotFoundError: MinIO is unavailable or
            template.html is missing -- both surface as 500 to the caller.
        jinja2.UndefinedError: The template referenced a context key
            the renderer didn't supply. StrictUndefined makes this a
            hard error instead of a silent empty string.
    """
    html_body = await get_template_html_cached(data.template.storage_prefix)

    asset_data_uri = await make_asset_data_uri_func(
        data.template.storage_prefix,
        data.template.asset_files,
    )

    # SEC-NEW-01 closure (R2 §5.4): autoescape + StrictUndefined are
    # mandatory at render time. autoescape blocks stored-XSS through
    # user-controlled fields (investor_name, company.description, ...);
    # StrictUndefined fails loudly on a missing placeholder rather
    # than producing a document with literal Jinja syntax.
    env = Environment(
        autoescape=True,
        undefined=StrictUndefined,
    )
    env.globals["asset_data_uri"] = asset_data_uri

    template_obj = env.from_string(html_body)

    now = datetime.now(UTC)
    context = {
        "investor_name": data.investor_name,
        # Bootstrap purchase_agreement templates (R2 §4.4) reference
        # `investor_email` directly. NULL credentials would Jinja-print
        # as "None" inside autoescape; force an empty string instead.
        "investor_email": data.investor_email or "",
        "company_name": data.company.name,
        # R2 §4.4 lists `company_legal_name` as a placeholder. CompanyProfile
        # has no dedicated legal-name column; we render the same `name`
        # value into both placeholders.
        "company_legal_name": data.company.name,
        "company_logo_url": data.company.logo_url,
        "product_name": data.product.name,
        "units": data.purchase.units,
        # Bootstrap templates take raw cents (they format inline in the
        # locale-specific HTML). The pre-formatted *_display strings are
        # kept alongside for any company-overridden template that wants
        # them, but a bootstrap render uses the raw ints.
        "paid_cents": data.purchase.paid_cents,
        "paid_display": format_cents(data.purchase.paid_cents),
        "price_per_unit_cents": data.purchase.price_per_unit_cents,
        "price_per_unit_display": format_cents(
            data.purchase.price_per_unit_cents
        ),
        "legal_basis": data.purchase.legal_basis,
        "purchase_date": data.purchase.created_at.strftime("%B %d, %Y"),
        "issue_date": now.strftime("%B %d, %Y"),
        "certificate_number": _short_id(data.purchase.id),
    }

    return template_obj.render(**context)


def generate_agreement_pdf(html: str) -> bytes:
    """Convert agreement HTML to PDF bytes via xhtml2pdf.

    A converter failure on rendered HTML is a server-side problem
    (either a broken template that Staff uploaded or an xhtml2pdf
    regression), not a client mistake -- the investor did nothing
    wrong by asking for their document. Round 11 ERR-11-01 reclassifies
    this as 500 with a stable `code` so Sentry / Staff dashboards can
    aggregate it separately from genuine 400s.
    """
    from xhtml2pdf import pisa

    buffer = io.BytesIO()
    result = pisa.CreatePDF(io.StringIO(html), dest=buffer)

    if result.err:
        logger.error("agreement_pdf_generation_failed", errors=result.err)
        raise AivisError(
            message="Failed to generate agreement PDF",
            code="pdf_generation_failed",
            status_code=500,
        )

    return buffer.getvalue()


async def send_agreement_email(
    data: AgreementData,
    pdf_bytes: bytes,
) -> bool:
    """Send the agreement PDF to the investor's email.

    Uses core/email.send_email() with the full SMTP/Mailgun routing
    logic (high-secured domains, fallback). Raises BadRequestError if
    the investor has no email on record.
    """
    if not data.investor_email:
        raise BadRequestError("Investor has no email address on file")

    agreement_number = _short_id(data.purchase.id)
    filename = f"agreement_{agreement_number}.pdf"

    success = await send_email(
        recipient=data.investor_email,
        subject=f"Purchase Agreement -- {agreement_number}",
        body=(
            f"Dear {data.investor_name},\n\n"
            f"Please find your purchase agreement attached.\n\n"
            f"Agreement: {agreement_number}\n"
            f"Company: {data.company.name}\n"
            f"Product: {data.product.name}\n"
            f"Units: {data.purchase.units}\n"
            f"Total paid: {format_cents(data.purchase.paid_cents)}\n\n"
            f"Best regards,\n"
            f"AIVIS.ONE Platform"
        ),
        attachment=(filename, pdf_bytes, "application/pdf"),
    )

    if success:
        logger.info(
            "agreement_email_sent",
            purchase_id=str(data.purchase.id),
        )
    else:
        logger.error(
            "agreement_email_failed",
            purchase_id=str(data.purchase.id),
        )

    return success
