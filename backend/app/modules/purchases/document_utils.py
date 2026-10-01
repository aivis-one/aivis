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
#   documents_link         -- the address of one document, for its email
#
# All four are pure -- they only read their inputs (or settings) and
# return a value. No DB / MinIO / Redis access; safe to call inside any
# render path.
# =============================================================================

from uuid import UUID

from app.core.config import settings
from app.modules.users.models import User


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
