# =============================================================================
# AIVIS.ONE Backend -- Purchase Document Helpers (Refactor 2 iter 2.4, R2 §5.4)
# =============================================================================
#
# Shared, side-effect-free helpers used by BOTH per-Purchase agreements
# (agreement_service) and live ownership certificates
# (ownership_certificate_service). Lives here, in its own module, so
# neither service imports private (`_underscore`) symbols out of the
# other one -- the previous shape leaked agreement_service internals
# into ownership_certificate_service and made future renames in either
# direction risky (Round 11 QC-11-01).
#
# Functions:
#   extract_investor_name  -- best-effort display name from User.profile
#   extract_investor_email -- email address from User.credentials JSONB
#   format_cents           -- "150000" -> "1,500.00"
#   format_document_date   -- a date in the document's language
#   format_document_datetime -- a date and the UTC time, the same way
#   documents_link        -- the address of one document, for its email
#   build_document_environment -- THE Jinja2 environment for document
#                             templates (renderers and reconcile, H34 P-128)
#
# All of them are pure -- they only read their inputs (or settings) and
# return a value. No DB / MinIO / Redis access; safe to call inside any
# render path.
# =============================================================================

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from jinja2 import Environment, StrictUndefined

from app.core.config import settings
from app.modules.users.models import User


def build_document_environment(
    asset_data_uri: Callable[[str], str] | None,
) -> Environment:
    """The one Jinja2 environment every document template is held to.

    ONE FACTORY, THREE CALLERS (H34 P-128): the agreement renderer, the
    ownership-certificate renderer, and template reconcile
    (scripts/_template_reconcile_core.py), which COMPILES each template
    with it before accepting it. Reconcile used to parse with a bare
    Environment(), which catches syntax but not what only compilation
    sees -- a filter or test that does not exist -- so such a template was
    accepted and then failed on every render. Compiled here by the same
    environment the renderers use (plus, in reconcile, a by-name check of
    the filters and tests Jinja2 defers to render time inside
    conditions), it is refused at the door instead. A second,
    hand-written environment in any of the three places would reopen
    exactly that gap the day the two drift apart: a filter registered in
    one and not the other.

    SEC-NEW-01 (R2 §5.4): autoescape blocks stored XSS through
    user-controlled fields (investor_name, company.description, ...);
    StrictUndefined makes a missing placeholder a hard error instead of a
    document with an empty hole in it.

    Args:
        asset_data_uri: the template's asset_data_uri global (see
            companies/service.py::make_asset_data_uri_func). Renderers
            pass it; reconcile passes None, because it only compiles: a
            global is looked up when the template RENDERS, so compiling
            with or without it produces the same code.
    """
    env = Environment(
        autoescape=True,
        undefined=StrictUndefined,
    )
    if asset_data_uri is not None:
        env.globals["asset_data_uri"] = asset_data_uri
    return env


def extract_investor_name(user: User) -> str:
    """Extract a human-readable display name from User.profile JSONB.

    Falls back to the email local-part, then to a generic "Investor".
    Identical heuristic to the Sprint 9.2 certificate_service so
    existing data renders the same way.
    """
    if user.profile:
        first = user.profile.get("first_name", "")
        last = user.profile.get("last_name", "")
        full = f"{first} {last}".strip()
        if full:
            return full

    email_creds = (user.credentials or {}).get("email", {})
    email_addr = email_creds.get("email", "")
    if email_addr and "@" in email_addr:
        return email_addr.split("@")[0]

    return "Investor"


def extract_investor_email(user: User) -> str | None:
    """Extract email address from User.credentials JSONB."""
    email_creds = (user.credentials or {}).get("email", {})
    return email_creds.get("email")


def format_cents(cents: int) -> str:
    """Format cents as a thousands-grouped dollar string.

    150000 -> '1,500.00'. Same formatter the Sprint 9.2 certificate
    used; templates that consumed `paid_display` keep working.
    """
    dollars = cents / 100
    return f"{dollars:,.2f}"


# Russian month names in the genitive case ("23 октября 2026 г.").
_RU_MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def format_document_date(dt: datetime, language: str) -> str:
    """A date as a document of the given language prints it.

    ru -> '23 октября 2026 г.'; every other language -> 'October 23, 2026'
    (the English form the templates printed before). Pure; the month
    names live here so no template carries a month table.
    """
    if language == "ru":
        return f"{dt.day} {_RU_MONTHS_GENITIVE[dt.month - 1]} {dt.year} г."
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def format_document_datetime(dt: datetime, language: str) -> str:
    """A date and the time of day in UTC, in the document's language:
    '23 октября 2026 г., 14:05 UTC' / 'October 23, 2026, 14:05 UTC'.
    A naive datetime is taken as UTC."""
    moment = dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
    return f"{format_document_date(moment, language)}, {moment:%H:%M} UTC"


def documents_link(company_id: UUID, purchase_id: UUID | None = None) -> str:
    """Where a document email points the reader: the document itself.

    ONE PLACE, ON PURPOSE. Both document emails (per-purchase agreement
    and per-company ownership certificate) carry a link rather than an
    attachment -- comms delivers no attachments and is not going to --
    and this function is the single line that decides where that link
    goes.

    THE SHAPE. `{FRONTEND_BASE_URL}/portfolio/{company_id}` plus a query
    naming the document:
      purchase_id given -> `?doc=agreement&purchase={purchase_id}`
                           (an agreement belongs to ONE purchase);
      purchase_id None  -> `?doc=ownership`
                           (a certificate belongs to the investor's
                           whole position in the company, there is no
                           purchase to name).
    The frontend reads that query on the company position screen and
    opens the named document over it.

    WHY A ROLE-NEUTRAL PATH. The position screen exists twice, under the
    investor shell and under the agent shell, and the purchaser's role
    is in neither document's data carrier. `/portfolio/:id` is a
    frontend route with no shell of its own: after sign-in it sends the
    reader into the shell of the role they actually have, with the
    query intact. The role is decided where it is known -- in the
    browser, after sign-in -- not guessed here inside a mail body.

    WHY NO TOKEN. This product sets no cookies -- authorization is a
    Bearer header and nothing else -- so a browser following a link out
    of a mail client carries no credentials. A link that opened the
    document by itself would have to carry its own token, which is a
    key living in a forwardable message for a paper people come back to
    years later. Owner's decision: no token. An anonymous reader is sent
    to sign in and lands on the same document afterwards (the router
    carries the requested URL through `?next=`), and the email says so.
    """
    base = f"{settings.frontend_base_url}/portfolio/{company_id}"
    if purchase_id is None:
        return f"{base}?doc=ownership"
    return f"{base}?doc=agreement&purchase={purchase_id}"
