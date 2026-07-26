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
#
# All three are pure -- they only read their inputs and return a value.
# No DB / MinIO / Redis access; safe to call inside any render path.
# =============================================================================

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
