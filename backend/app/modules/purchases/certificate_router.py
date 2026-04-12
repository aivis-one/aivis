# =============================================================================
# CBSHOME Backend -- Certificate Router (Sprint 9.2)
# =============================================================================
#
# ENDPOINTS:
#   GET  /api/v1/purchases/{id}/certificate       -- view as HTML
#   POST /api/v1/purchases/{id}/certificate/email  -- send PDF to email
#
# AUTH:
#   Requires authenticated user. Only purchase owner can access.
#   Avatar mode works automatically (get_current_user returns target user).
#
# HTML RESPONSE:
#   GET returns Content-Type: text/html. Frontend displays in iframe or
#   new window. User can print/save as PDF via browser Ctrl+P.
#
# EMAIL:
#   POST generates PDF via xhtml2pdf, sends to investor's email via
#   core/email with full SMTP/Mailgun/high-secured routing.
#   Rate-limited per user to prevent SMTP abuse and inbox flooding.
#
# COMMIT RULE (P-01):
#   Read-only endpoints use get_db_reader. POST /email does not
#   write to DB (email sending is external side-effect).
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.rate_limit import check_rate_limit
from app.modules.auth.dependencies import get_current_user
from app.modules.purchases.certificate_service import (
    generate_certificate_pdf,
    load_certificate_data,
    render_certificate_html,
    send_certificate_email,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/purchases", tags=["certificates"])


@router.get(
    "/{purchase_id}/certificate",
    response_class=HTMLResponse,
)
async def view_certificate(
    purchase_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> HTMLResponse:
    """View purchase certificate as HTML.

    Returns rendered HTML page. Frontend displays in iframe or new window.
    User can save as PDF via browser print dialog (Ctrl+P).
    """
    data = await load_certificate_data(purchase_id, user.id, session)
    html = render_certificate_html(data)
    return HTMLResponse(content=html)


@router.post(
    "/{purchase_id}/certificate/email",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def email_certificate(
    purchase_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> None:
    """Send purchase certificate as PDF to investor's email.

    Generates PDF from HTML template via xhtml2pdf, then sends
    via SMTP/Mailgun with the full routing logic (high-secured
    domains, fallback).

    Rate-limited to prevent SMTP abuse and Mailgun billing spikes.
    """
    await check_rate_limit(f"cert_email:{user.id}")

    data = await load_certificate_data(purchase_id, user.id, session)
    html = render_certificate_html(data)
    pdf_bytes = generate_certificate_pdf(html)
    await send_certificate_email(data, pdf_bytes)
