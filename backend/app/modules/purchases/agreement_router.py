# =============================================================================
# AIVIS.ONE Backend -- Agreement & Ownership Router (Refactor 2 iter 2.4,
#                                                    R2 §5.3)
# =============================================================================
#
# ENDPOINTS:
#   GET  /api/v1/purchases/{id}/agreement              -- HTML render
#   POST /api/v1/purchases/{id}/agreement/email        -- PDF to email (204)
#   GET  /api/v1/companies/{id}/ownership-certificate         -- HTML render
#   POST /api/v1/companies/{id}/ownership-certificate/email   -- PDF to email (204)
#
# REPLACES (Sprint 9.2):
#   purchases/certificate_router.py exposed
#     GET  /api/v1/purchases/{id}/certificate
#     POST /api/v1/purchases/{id}/certificate/email
#   That router and its supporting service file are deleted in iter 2.4.
#   The rename is a BREAKING CHANGE -- no 301/302 from the old paths
#   (R2 §5.3). The frontend ships its own update in iter 2.5+.
#
# WHY TWO PREFIXES IN ONE FILE:
#   The four endpoints serve two related-but-distinct resources:
#     - per-Purchase agreement      (snapshot, /api/v1/purchases)
#     - per-investor-company cert   (live aggregate, /api/v1/companies)
#   Both are document-rendering paths over the same Jinja2 / MinIO
#   machinery, so it's natural to keep them together. We
#   expose two APIRouter objects (agreement_router, ownership_router)
#   with distinct prefixes, both wired in main.py.
#
# AUTH:
#   All endpoints require an authenticated user (any role).
#   Avatar mode works automatically (get_current_user returns target user).
#   The per-Purchase load returns 404 if the caller isn't the owner.
#   The ownership endpoint scopes to (current_user, company_id).
#
# RATE LIMITING:
#   POST /email endpoints use the existing per-user check_rate_limit
#   helper to prevent SMTP abuse and Mailgun billing spikes. Keys:
#     agreement_email:{user.id}
#     ownership_email:{user.id}
#   The default auth-flow window (5/60s) is acceptable for human-driven
#   "email me my doc" clicks; daemons / staff don't use these.
#
# 500 ON BROKEN TEMPLATE STATE (R2 §5.3):
#   load_agreement_data raises TemplateMissingError when the Purchase
#   row exists but template_id is NULL; render_ownership_html raises
#   the same when the 4-stage fallback finds nothing. Both surface to
#   the AivisError handler as 500 with code "agreement_template_missing"
#   and the message "The agreement for this purchase is not configured
#   (system error)". Clients match on the CODE, never on the message.
#
# COMMIT RULE (P-01):
#   The two GET endpoints render and return -- get_db_reader.
#   The two POST /email endpoints DO write to the DB: asking comms for a
#   letter is an outbox row in the request's transaction, not an
#   external side effect, so they take get_db_session. A reader session
#   there would roll the row away and still answer 204.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.rate_limit import check_rate_limit
from app.modules.auth.dependencies import get_current_user
from app.modules.purchases.agreement_service import (
    load_agreement_data,
    render_agreement_html,
    request_agreement_email,
)
from app.modules.purchases.ownership_certificate_service import (
    load_ownership_data,
    render_ownership_html,
    request_ownership_email,
)
from app.modules.users.models import User

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Per-Purchase agreement (snapshot)
# ---------------------------------------------------------------------------


agreement_router = APIRouter(
    prefix="/api/v1/purchases",
    tags=["agreements"],
)


@agreement_router.get(
    "/{purchase_id}/agreement",
    response_class=HTMLResponse,
)
async def view_agreement(
    purchase_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> HTMLResponse:
    """Render the per-Purchase agreement as HTML.

    Returns the rendered HTML for embedding in an iframe or browser
    print-to-PDF. 404 if the caller doesn't own the Purchase or it's
    been reversed; 500 if the Purchase exists but template_id is NULL
    (R2 §5.3 -- broken-infra signal, not a 404).
    """
    data = await load_agreement_data(purchase_id, user.id, session)
    html = await render_agreement_html(data, session)
    return HTMLResponse(content=html)


@agreement_router.post(
    "/{purchase_id}/agreement/email",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def email_agreement(
    purchase_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Ask comms to email the investor a link to their agreement.

    Same auth + template-missing semantics as GET. Rate-limited per
    user under key `agreement_email:<user_id>` to keep provider spend
    bounded.

    get_db_session, NOT get_db_reader, AND THAT IS LOAD-BEARING. The
    reader session rolls back unconditionally in its `finally` (see
    core/database.py) -- correct for a GET, fatal here: the letter is
    now an INSERT into the outbox inside this request's transaction, so
    on a reader session the row would be written, logged as emitted,
    discarded by that rollback, and the endpoint would still answer
    204. No error anywhere, and no email, ever.
    """
    await check_rate_limit(f"agreement_email:{user.id}")

    data = await load_agreement_data(purchase_id, user.id, session)
    await request_agreement_email(data, session)


# ---------------------------------------------------------------------------
# Per-investor-company ownership certificate (live aggregate)
# ---------------------------------------------------------------------------


ownership_router = APIRouter(
    prefix="/api/v1/companies",
    tags=["ownership-certificates"],
)


@ownership_router.get(
    "/{company_id}/ownership-certificate",
    response_class=HTMLResponse,
)
async def view_ownership_certificate(
    company_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> HTMLResponse:
    """Render the live ownership certificate for (current_user, company_id).

    Aggregates all of the caller's non-reversed Purchases for the given
    company. 404 if the company doesn't exist or the caller has zero
    active Purchases there; 500 if the template lookup misses across
    all 4 fallback stages.
    """
    data = await load_ownership_data(company_id, user.id, session)
    html = await render_ownership_html(data, session)
    return HTMLResponse(content=html)


@ownership_router.post(
    "/{company_id}/ownership-certificate/email",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def email_ownership_certificate(
    company_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Ask comms to email the investor a link to their certificate.

    Same auth + 404 + 500 semantics as GET. Rate-limited per user under
    key `ownership_email:<user_id>`.

    get_db_session for the same reason as email_agreement above: the
    emission is an INSERT in this transaction, and a reader session
    would silently roll it away.
    """
    await check_rate_limit(f"ownership_email:{user.id}")

    data = await load_ownership_data(company_id, user.id, session)
    await request_ownership_email(data, session)
