# =============================================================================
# AIVIS.ONE Backend -- "Log In With Telegram" on the website (H45)
# =============================================================================
#
# Telegram's current website login is OpenID Connect (core.telegram.org/bots/
# telegram-login); the iframe widget signed with SHA256(bot token) is archived
# there as "legacy" and is NOT used. The mechanism follows VELO's
# telegram_oidc.py (BE-141); the account model around it is this product's.
#
# ONE BRICK, "a code from Telegram (+ PKCE) -> a verified Telegram user":
#
#   start_login()     -> where to send the browser (oauth.telegram.org/auth)
#                        and the PKCE verifier the caller keeps until the
#                        callback, next to its own `state`;
#   complete_login()  -> on the callback: the code exchanged at
#                        oauth.telegram.org/token (HTTP Basic with the client
#                        secret, plus the verifier), the id_token verified
#                        against Telegram's published keys -- signature, iss,
#                        aud (= our client id), exp, iat -- and returned as a
#                        TelegramUser;
#   as_init_data_user() -> THE ONE TRANSLATOR of a TelegramUser into the user
#                        dict the Mini App's initData gives
#                        (auth/telegram.py::validate_telegram_init_data), so
#                        that everything after the proof -- the rate limit,
#                        upsert_telegram_user, the link token, the second
#                        factor, the session -- is the Mini App's own code.
#
# It knows nothing about users or sessions; auth/web_login.py keeps the state
# of a started sign-in and auth/router.py runs the shared path.
#
# CLAIMS (scope "openid profile"): `id` -- the Telegram user id, the same
# number initData carries; `given_name` / `family_name` / `name`,
# `preferred_username`, `picture`. `sub` is a different, OIDC-only identifier
# and is not used. There is no language claim: the translator gives
# language_code None and the caller passes the site's interface language on
# its own (web_login.py).
#
# THE BOT'S RIGHT TO WRITE (scope telegram:bot_access) IS NOT ASKED (owner
# ruling, H45 gate): no customer notification goes out by Telegram today, so
# the right would be used for nothing. When customer Telegram notifications
# appear, add telegram:bot_access to SCOPE -- a person who came only through
# the website and never opened the bot cannot be written to without it.
#
# SECRETS. The client secret, the code, the verifier and the id_token are
# never logged; a failure is logged as a reason word and, for an HTTP answer,
# its status code.
#
# HTTP. Two requests to Telegram per sign-in (token, keys). The caller makes
# them OUTSIDE any database transaction (par0 §8): in the complete route they
# run before the first statement of the request's session. Keys are fetched
# per sign-in, not cached: a sign-in is rare, and a cache would be one more
# thing to be stale when Telegram rotates them.
# =============================================================================

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
import structlog

from app.core.config import settings

logger = structlog.get_logger()

ISSUER = "https://oauth.telegram.org"
AUTHORIZE_URL = f"{ISSUER}/auth"
TOKEN_URL = f"{ISSUER}/token"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
SCOPE = "openid profile"
# RS256 is Telegram's default; ES256 is the other algorithm BotFather offers
# that still allows the profile scope (EdDSA and ES256K are openid-only).
ALGORITHMS = ("RS256", "ES256")


class TelegramLoginError(Exception):
    """The sign-in did not prove a Telegram user. `reason` is a word for the
    log; the phrase the person reads is the caller's."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class TelegramLoginStart:
    """What start_login hands the caller: the URL to send the browser to,
    and the verifier to keep (next to its own `state`) until the callback."""

    url: str
    code_verifier: str


@dataclass(frozen=True)
class TelegramUser:
    """A Telegram user the id_token proved."""

    telegram_id: int
    first_name: str | None
    last_name: str | None
    username: str | None
    photo_url: str | None


def configured() -> bool:
    """Both keys are set (config.py refuses a start with only one)."""
    return bool(
        settings.telegram_login_client_id and settings.telegram_login_client_secret
    )


def _pkce_challenge(verifier: str) -> str:
    """S256 challenge of a verifier (RFC 7636 §4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def start_login(*, redirect_uri: str, state: str) -> TelegramLoginStart:
    """The browser's way to Telegram. `state` is the caller's (it finds its
    own record by it on the callback); the verifier is made here and must
    come back to complete_login."""
    verifier = secrets.token_urlsafe(48)
    url = f"{AUTHORIZE_URL}?" + urlencode(
        {
            "client_id": settings.telegram_login_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return TelegramLoginStart(url=url, code_verifier=verifier)


def _client() -> httpx.AsyncClient:
    """The HTTP client of both calls. A function so tests can hand in a mock
    transport; production gets a plain client with the timeout."""
    return httpx.AsyncClient(timeout=settings.telegram_login_http_timeout_seconds)


async def complete_login(
    *, code: str, redirect_uri: str, code_verifier: str
) -> TelegramUser:
    """Exchange the code and verify the id_token. Raises TelegramLoginError."""
    client_id = settings.telegram_login_client_id
    try:
        async with _client() as http:
            resp = await http.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "code_verifier": code_verifier,
                },
                auth=(client_id, settings.telegram_login_client_secret),
            )
            if resp.status_code != 200:
                logger.warning("telegram_login_token_refused", status=resp.status_code)
                raise TelegramLoginError("token_refused")
            id_token = _id_token(resp.json())

            keys = await http.get(JWKS_URL)
            if keys.status_code != 200:
                logger.warning(
                    "telegram_login_keys_unavailable", status=keys.status_code
                )
                raise TelegramLoginError("keys_unavailable")
            jwks = keys.json()
    except httpx.HTTPError as exc:
        logger.warning("telegram_login_unreachable", error=type(exc).__name__)
        raise TelegramLoginError("unreachable") from None
    except ValueError:
        # resp.json() / keys.json() on a body that is not JSON.
        logger.warning("telegram_login_bad_response")
        raise TelegramLoginError("bad_response") from None
    return verify_id_token(id_token, jwks)


def _id_token(body: object) -> str:
    value = body.get("id_token") if isinstance(body, dict) else None
    if not isinstance(value, str) or not value:
        raise TelegramLoginError("no_id_token")
    return value


def verify_id_token(id_token: str, jwks: object) -> TelegramUser:
    """Signature against the published key named by the token's kid, then
    iss, aud, exp and iat (all required), then the Telegram user id. Raises
    TelegramLoginError."""
    try:
        header = jwt.get_unverified_header(id_token)
        alg = header.get("alg")
        if alg not in ALGORITHMS:
            raise TelegramLoginError("bad_algorithm")
        key_set = jwt.PyJWKSet.from_dict(jwks)  # type: ignore[arg-type]
        kid = header.get("kid")
        candidates = [k for k in key_set.keys if kid is None or k.key_id == kid]
        if len(candidates) != 1:
            raise TelegramLoginError("unknown_key")
        claims = jwt.decode(
            id_token,
            candidates[0].key,
            algorithms=[alg],
            audience=settings.telegram_login_client_id,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except TelegramLoginError:
        raise
    except (jwt.PyJWTError, TypeError, KeyError, ValueError, AttributeError) as exc:
        logger.info("telegram_login_id_token_rejected", error=type(exc).__name__)
        raise TelegramLoginError("bad_id_token") from None

    telegram_id = _telegram_id(claims.get("id"))
    if telegram_id is None:
        # Presence, type and the claim NAMES -- never a value.
        logger.warning(
            "telegram_login_id_rejected",
            has_id="id" in claims,
            id_type=type(claims.get("id")).__name__,
            claims=sorted(claims),
        )
        raise TelegramLoginError("no_telegram_id")
    return TelegramUser(
        telegram_id=telegram_id,
        first_name=_text(claims.get("given_name")) or _text(claims.get("name")),
        last_name=_text(claims.get("family_name")),
        username=_text(claims.get("preferred_username")),
        photo_url=_https(claims.get("picture")),
    )


def as_init_data_user(user: TelegramUser) -> dict[str, Any]:
    """THE translator: a proved Telegram user in the shape of the Mini App's
    initData `user` -- the dict validate_telegram_init_data returns and the
    shared sign-in path (auth/router.py::_telegram_sign_in) takes. The id is a
    number; a claim Telegram did not send is None, as a field initData leaves
    out. language_code is None: OpenID Connect carries no language, and the
    shared upsert keeps the one an earlier Mini App sign-in stored
    (auth/service.py::upsert_telegram_user)."""
    return {
        "id": user.telegram_id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "photo_url": user.photo_url,
        "language_code": None,
    }


# credentials.telegram.id is read as BIGINT (the ix_users_telegram_id cast).
_BIGINT_MAX = 2**63 - 1
_ASCII_DIGITS = re.compile(r"[0-9]+")


def _telegram_id(value: object) -> int | None:
    """The Telegram user id from the `id` claim, or None.

    Telegram's example shows a JSON number, but VELO's live check (BE-141
    FIX) met a string there. So: a JSON integer, or a string of ASCII digits
    only (leading zeros allowed; no sign, space, underscore or another
    script's digits -- int() and str.isdigit() would take some of those,
    hence the pattern first), in 1..BIGINT. A JSON true/false is not an id,
    though bool is an int to Python.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and _ASCII_DIGITS.fullmatch(value):
        digits = value.lstrip("0")
        # Length first: int() refuses strings past 4300 digits with an
        # exception, and nothing past 19 digits fits BIGINT anyway.
        if len(digits) > len(str(_BIGINT_MAX)):
            return None
        number = int(digits or "0")
    else:
        return None
    return number if 1 <= number <= _BIGINT_MAX else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _https(value: object) -> str | None:
    """A photo URL is shown in an <img>: https only, anything else dropped."""
    text = _text(value)
    return text if text is not None and text.startswith("https://") else None
