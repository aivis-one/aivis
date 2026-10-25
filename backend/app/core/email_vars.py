# =============================================================================
# AIVIS.ONE Backend -- the variables every e-mail letter shares
# =============================================================================
#
# comms renders a letter from the profile's templates
# (comms-profile/templates/<locale>.yaml) with str.format_map over the
# notification's `action_data`. A template may carry no domain literal
# (comms' profile loader refuses it), so every address a letter shows
# reaches it here, as a variable, assembled at send time from settings:
#
#   support_url    the support bot a reader is sent to (SUPPORT_URL; else the
#                  installer's TELEGRAM_BOT_URL; else the site's address)
#   support_email  the company's public mailbox (SUPPORT_EMAIL; hello@ on
#                  the site's host when it is not set)
#   cabinet_url    the cabinet's address (FRONTEND_BASE_URL)
#   site_url       the public site's origin
#   logo_url       the letter's logo, a PNG the site build publishes at
#                  /email/logo.png
#
# The language of a letter is not decided here: comms takes it from the
# recipient's `locale` (core/comms.py::user_snapshot sends the user's own).
#
# site_host() is the same parse of FRONTEND_BASE_URL, public for the seed
# (scripts/seed.py), which builds its addresses on the box's own host.
# =============================================================================

from typing import Any
from urllib.parse import urlsplit

from app.core.config import settings

LOGO_PATH = "/email/logo.png"


def _site(frontend_base_url: str) -> tuple[str, str]:
    """-> (origin, host) of the cabinet's address; ("", "") when it has none."""
    parts = urlsplit(frontend_base_url.strip())
    if not parts.scheme or not parts.netloc:
        return "", ""
    return f"{parts.scheme}://{parts.netloc}", parts.hostname or ""


def site_host() -> str:
    """The host of the cabinet's address (FRONTEND_BASE_URL), or "".

    The one parse of that address, shared: the letters build their
    hello@<host> from it, and the seed (scripts/seed.py, H37) builds every
    seeded e-mail address on it.
    """
    return _site(settings.frontend_base_url)[1]


def email_action_data(**fields: Any) -> dict[str, Any]:
    """action_data for a letter: the shared addresses plus the type's own
    fields. Every value is a scalar (comms refuses anything else); a None
    becomes an empty string so a template never prints the word None."""
    site, host = _site(settings.frontend_base_url)
    data: dict[str, Any] = {
        "support_url": settings.support_url or settings.telegram_bot_url or site,
        "support_email": settings.support_email or (f"hello@{host}" if host else ""),
        "cabinet_url": settings.frontend_base_url.rstrip("/"),
        "site_url": site,
        "logo_url": f"{site}{LOGO_PATH}" if site else "",
    }
    for key, value in fields.items():
        data[key] = "" if value is None else value
    return data
