# =============================================================================
# AIVIS.ONE Backend -- the variables every e-mail letter shares
# =============================================================================
#
# The backend builds its letters itself (app/letters, H43): every address a
# letter shows reaches it here, as a variable, assembled at build time from
# settings -- a word in app/letters/copy.yaml carries no domain literal
# (checks/deploy_addresses.py), only the variable:
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
# The language of a letter is decided by the builder from the person's own
# users.language (app/letters letter_language), not here.
#
# site_host() is the same parse of FRONTEND_BASE_URL, public for the seed
# (scripts/seed.py), which builds its addresses on the box's own host.
# =============================================================================

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


def letter_vars() -> dict[str, str]:
    """The addresses every letter may show, as the builder's variables.

    A setting that is not set gives an empty string, never None: the
    builder refuses a None (app/letters), and an address a deploy does not
    have is printed as nothing rather than refusing every letter."""
    site, host = _site(settings.frontend_base_url)
    return {
        "support_url": settings.support_url or settings.telegram_bot_url or site,
        "support_email": settings.support_email or (f"hello@{host}" if host else ""),
        "cabinet_url": settings.frontend_base_url.rstrip("/"),
        "site_url": site,
        "logo_url": f"{site}{LOGO_PATH}" if site else "",
    }
