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
#   documents_link         -- where a document email sends the reader
#
# All four are pure -- they only read their inputs (or settings) and
# return a value. No DB / MinIO / Redis access; safe to call inside any
# render path.
# =============================================================================

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


def documents_link() -> str:
    """Where a document email points the reader.

    ONE PLACE, ON PURPOSE. Both document emails (per-purchase agreement
    and per-company ownership certificate) carry a link rather than an
    attachment -- comms delivers no attachments and is not going to --
    and this function is the single line that decides where that link
    goes. Moving it is a one-line change, which is the whole reason it
    is a function and not a formatted string in two emitters.

    WHY A DESTINATION AND NOT THE DOCUMENT. This product sets no
    cookies -- authorization is a Bearer header and nothing else -- so a
    browser following a link out of a mail client carries no
    credentials, and the backend has no way to know who arrived. A
    document URL would therefore have to carry its own token, which is a
    key living in a forwardable message for a paper people come back to
    years later. So the link lands the reader on a screen they must be
    logged in to see, and the email says so in as many words.

    KNOWN LIMIT, NAMED HERE RATHER THAN DISCOVERED LATER: the portfolio
    lives under the investor shell, and the agent shell has its own
    copy of the same route (`/agent/portfolio`). A purchaser whose role
    is agent follows this link to a screen their shell does not serve.
    The role is not in either document's data carrier, and inventing a
    role lookup inside a mail body is not this change's business -- when
    a document route exists, this line points at it and the question
    disappears.
    """
    return f"{settings.frontend_base_url}/investor/portfolio"
