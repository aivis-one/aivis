# =============================================================================
# AIVIS.ONE Backend -- Telegram bot webhook (/start welcome)
# =============================================================================
#
# ENDPOINT:
#   POST /api/v1/telegram/webhook  -- Telegram calls it for every update of the
#                                     bot (registered once by
#                                     scripts/install_aivis.sh with setWebhook
#                                     and a secret_token).
#
# WHAT IT DOES. Answers a private-chat /start with a welcome and an inline
# button that opens the cabinet as a Mini App. The reply travels in the BODY of
# the webhook response (the Bot API's "answer to the webhook": the response is
# itself the method call), so there is no outgoing request per update and no
# bot-token call from this process. Every other update is ignored with an empty
# 200, which is what Telegram needs to stop retrying it.
#
# THE SECRET. Telegram echoes the secret_token given at setWebhook in the
# X-Telegram-Bot-Api-Secret-Token header (1-256 characters: letters, digits,
# `_`, `-`). The route compares it, in constant time, with
# settings.telegram_webhook_secret and refuses everything else; with the
# setting empty it refuses every call (fail closed).
#
# comms only SENDS (it has no inbound webhook), so this route collides with
# nothing there.
#
# THE TEXTS BELOW are the bot's approved welcome, English and Russian; the
# bot's name, about text, description and commands are set in BotFather and
# by setMyName / setMyShortDescription / setMyDescription / setMyCommands.
# =============================================================================

import hmac
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import ForbiddenError

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

# Keyed by language; any language without a text gets English.
WELCOME_TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "text": (
            "AIVIS.ONE — a visionary for visionaries.\n\n"
            "Your cabinet is one tap away: buy parts of projects and follow your holdings."
        ),
        "button": "Open cabinet",
    },
    "ru": {
        "text": (
            "AIVIS.ONE — визионер для визионеров.\n\n"
            "Ваш кабинет — в одно касание: покупайте части проектов и следите за своими долями."
        ),
        "button": "Открыть кабинет",
    },
}


def _is_start_command(text: Any) -> bool:
    """True for `/start`, `/start <payload>` and `/start@bot [payload]`."""
    if not isinstance(text, str):
        return False
    first = text.split(maxsplit=1)[0] if text.strip() else ""
    return first == "/start" or first.startswith("/start@")


def _welcome(chat_id: int, language_code: Any) -> dict[str, Any]:
    """The sendMessage call that is the webhook's answer."""
    is_ru = isinstance(language_code, str) and language_code[:2] == "ru"
    lang = "ru" if is_ru else "en"
    texts = WELCOME_TEXTS.get(lang) or WELCOME_TEXTS["en"]
    return {
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": texts["text"],
        "reply_markup": {
            "inline_keyboard": [
                [
                    {
                        "text": texts["button"],
                        "web_app": {"url": settings.frontend_base_url},
                    }
                ]
            ]
        },
    }


@router.post("/webhook", include_in_schema=False)
async def telegram_webhook(request: Request) -> JSONResponse:
    """Telegram update -> the /start welcome in the response body, else {}."""
    expected = settings.telegram_webhook_secret
    received = request.headers.get(SECRET_HEADER, "")
    if not expected or not hmac.compare_digest(
        received.encode(), expected.encode()
    ):
        logger.warning("telegram_webhook_refused", has_secret=bool(received))
        raise ForbiddenError("Forbidden", code="forbidden")

    try:
        update = await request.json()
    except ValueError:
        return JSONResponse({})
    if not isinstance(update, dict):
        return JSONResponse({})

    message = update.get("message")
    if not isinstance(message, dict):
        return JSONResponse({})
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("type") != "private":
        return JSONResponse({})
    chat_id = chat.get("id")
    if not isinstance(chat_id, int) or isinstance(chat_id, bool):
        return JSONResponse({})
    if not _is_start_command(message.get("text")):
        return JSONResponse({})

    sender = message.get("from")
    language_code = sender.get("language_code") if isinstance(sender, dict) else None
    return JSONResponse(_welcome(chat_id, language_code))
