# =============================================================================
# AIVIS.ONE Backend -- the website sign-in through Telegram: its state (H45)
# =============================================================================
#
# The cabinet opened in a browser has no initData. It signs in with "Log In
# With Telegram" (OpenID Connect, telegram_oidc.py):
#
#   1. start    -- the login or registration screen asks for Telegram's URL.
#                  A fresh `state` is made here; what the return will need is
#                  kept in Redis under its sha256 -- the PKCE verifier, the
#                  redirect URI, the referral code and the interface language
#                  the screen sent, and the sha256 of the browser's MARK (a
#                  random string the frontend made and keeps in localStorage);
#   2. Telegram  -- the person confirms; Telegram sends the browser back to
#                  RETURN_PATH on the frontend with `code` and `state`;
#   3. complete -- the frontend posts code, state and its mark. The state is
#                  TAKEN (GETDEL, once), the mark is compared with the stored
#                  hash BEFORE the code is exchanged, and only then Telegram
#                  is asked who this is (auth/router.py).
#
# WHY THE MARK (login CSRF). Without it, someone could start a sign-in with
# their own Telegram, stop at the return, and hand the return link to a
# victim: the victim's browser would be signed into the attacker's account.
# The mark lives only in the browser that started, so a return opened
# anywhere else is refused -- here, and before any request to Telegram (the
# frontend refuses it too, without calling us).
#
# THE RETURN ADDRESS is settings.frontend_base_url + RETURN_PATH: the site's
# own address, written by the installer from FRONTEND_DOMAIN (https outside
# development). Never taken from the client, and the one kept under the state
# is the one the code is exchanged with.
#
# THE REFERRAL CODE AND THE LANGUAGE ride under the state because the browser
# leaves for Telegram between the screen that knows them and the return; the
# link token of a Telegram id nobody holds is minted with them, as the Mini
# App mints it with its start_param and initData language.
#
# SECRETS. The state, the mark, the code and the verifier are never logged.
# The Redis key holds the sha256 of the state; the value holds the sha256 of
# the mark, never the mark itself.
# =============================================================================

import hashlib
import hmac
import json
import secrets

from app.core.config import settings
from app.core.redis import get_redis
from app.modules.auth import telegram_oidc

# The frontend path Telegram sends the browser back to. The same literal is
# RETURN_PATH in frontend/src/platform/webLogin.ts and the route of
# TelegramReturnView; the full address (frontend_base_url + this) is what the
# owner registers in BotFather and what `aivis telegram-login status` prints.
RETURN_PATH = "/auth/telegram/return"

# How long a started sign-in waits for its return. Telegram's own page is the
# slow part (the person confirms in the Telegram app).
LOGIN_TTL_SECONDS = 600

_KEY_PREFIX = "telegram_web:"


def return_url() -> str:
    """The redirect URI of the website sign-in."""
    return settings.frontend_base_url.rstrip("/") + RETURN_PATH


def available() -> bool:
    """The website sign-in is switched on (both keys set)."""
    return telegram_oidc.configured()


def _key(state: str) -> str:
    return _KEY_PREFIX + hashlib.sha256(state.encode()).hexdigest()


def _mark_hash(mark: str) -> str:
    return hashlib.sha256(mark.encode()).hexdigest()


async def start(
    *, mark: str, referral_code: str | None, language: str | None
) -> tuple[str, str]:
    """Begin a sign-in for the browser holding `mark`. Returns (Telegram URL,
    state)."""
    state = secrets.token_urlsafe(32)
    redirect_uri = return_url()
    login = telegram_oidc.start_login(redirect_uri=redirect_uri, state=state)
    await get_redis().set(
        _key(state),
        json.dumps(
            {
                "redirect_uri": redirect_uri,
                "verifier": login.code_verifier,
                "mark_hash": _mark_hash(mark),
                "referral_code": referral_code,
                "language": language,
            }
        ),
        ex=LOGIN_TTL_SECONDS,
    )
    return login.url, state


async def take(state: str) -> dict | None:
    """The started sign-in under `state`, ONCE (GETDEL): a second taker -- a
    reload, a double submit, another worker -- gets None."""
    raw = await get_redis().getdel(_key(state))
    return json.loads(raw) if raw is not None else None


def mark_matches(started: dict, mark: str) -> bool:
    """The browser presenting `mark` is the one that started the sign-in.
    Constant-time on the hashes."""
    return hmac.compare_digest(_mark_hash(mark), str(started.get("mark_hash", "")))
