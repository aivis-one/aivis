# =============================================================================
# CBSHOME Backend -- Notification Formatters (Sprint 8.1 + 8.2)
# =============================================================================
#
# RESPONSIBILITY:
#   Deliver a NotificationDelivery via its channel (telegram, email, etc.).
#
# ARCHITECTURE:
#   ChannelFormatter -- Protocol defining the deliver interface.
#   StubFormatter    -- Default implementation that always succeeds (logs only).
#   TelegramFormatter -- aiogram Bot.send_message (Sprint 8.2).
#   EmailFormatter   -- aiosmtplib (SMTP) + httpx (Mailgun fallback) (Sprint 8.2).
#
# LAZY INIT:
#   _init_formatters() is called once on first get_formatter() call.
#   Real token/host -> real formatter, TEST/empty -> StubFormatter.
#
# PERMANENT FAILURE:
#   TelegramFormatter: bot blocked (403), chat not found (400) -> PermanentDeliveryError.
#   EmailFormatter: no email in credentials -> PermanentDeliveryError.
#   Service layer catches PermanentDeliveryError and marks delivery as failed
#   without incrementing attempts.
#
# FORMATTER REGISTRY:
#   get_formatter(channel) returns the appropriate formatter instance.
# =============================================================================

from email.message import EmailMessage
from typing import Protocol

import structlog

from app.core.config import settings
from app.modules.notifications.constants import DeliveryChannel
from app.modules.notifications.models import Notification, NotificationDelivery
from app.modules.notifications.template_engine import render
from app.modules.users.models import User

logger = structlog.get_logger()


class PermanentDeliveryError(Exception):
    """Raised when delivery fails permanently and should not be retried.

    Examples: bot blocked by user, chat not found, no email in credentials.
    """


class ChannelFormatter(Protocol):
    """Protocol for channel-specific notification delivery."""

    async def deliver(
        self,
        notification: Notification,
        delivery: NotificationDelivery,
        user: User,
    ) -> bool:
        """Attempt to deliver a notification via this channel.

        Args:
            notification: The parent notification (title, body, action_data).
            delivery: The delivery record (user_id, channel, channel_options).
            user: The recipient user (credentials, profile, language).

        Returns:
            True if delivery succeeded, False otherwise.

        Raises:
            PermanentDeliveryError: If delivery failed permanently.
        """
        ...


class StubFormatter:
    """Stub formatter -- logs delivery and always succeeds.

    Used when real credentials are not configured (TEST mode).
    """

    async def deliver(
        self,
        notification: Notification,
        delivery: NotificationDelivery,
        user: User,
    ) -> bool:
        """Log the delivery attempt and return True."""
        logger.info(
            "stub_delivery",
            notification_id=str(notification.id),
            delivery_id=str(delivery.id),
            channel=delivery.channel,
            user_id=str(delivery.user_id),
            title=notification.title,
        )
        return True


class TelegramFormatter:
    """Deliver notifications via Telegram Bot API (aiogram)."""

    def __init__(self, bot_token: str) -> None:
        # Lazy import: aiogram is only needed when real token is configured.
        from aiogram import Bot

        self._bot = Bot(token=bot_token)

    async def deliver(
        self,
        notification: Notification,
        delivery: NotificationDelivery,
        user: User,
    ) -> bool:
        """Send a Telegram message to the user.

        Reads chat_id from user.credentials["telegram"]["id"].
        Renders template using user's language.

        Raises:
            PermanentDeliveryError: If user has no telegram credentials
                or bot is blocked / chat not found.
        """
        telegram_creds = (user.credentials or {}).get("telegram")
        if not telegram_creds or "id" not in telegram_creds:
            raise PermanentDeliveryError("User has no telegram credentials")

        chat_id = int(telegram_creds["id"])
        lang = getattr(user, "language", "en") or "en"

        # Build template variables from notification data.
        variables = _build_variables(notification)

        text = render(
            notification_type=notification.type,
            channel="telegram",
            field="body",
            lang=lang,
            variables=variables,
        )

        try:
            await self._bot.send_message(chat_id=chat_id, text=text)
            return True
        except Exception as exc:
            error_text = str(exc).lower()
            # Telegram API errors for blocked bot or invalid chat.
            if "forbidden" in error_text or "chat not found" in error_text:
                raise PermanentDeliveryError(
                    f"Telegram permanent failure: {exc}"
                ) from exc
            # Transient error -- let retry handle it.
            raise


class EmailFormatter:
    """Deliver notifications via SMTP (primary) + Mailgun (fallback).

    High-secured domains (configured in settings) go directly to Mailgun,
    bypassing SMTP. All other domains try SMTP first, then Mailgun on failure.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_email: str,
        use_tls: bool,
        mailgun_api_key: str,
        mailgun_domain: str,
    ) -> None:
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._from_email = from_email
        self._use_tls = use_tls
        self._mailgun_api_key = mailgun_api_key
        self._mailgun_domain = mailgun_domain

    async def deliver(
        self,
        notification: Notification,
        delivery: NotificationDelivery,
        user: User,
    ) -> bool:
        """Send an email to the user.

        Reads email from user.credentials["email"]["email"].
        Renders subject + body templates using user's language.

        Raises:
            PermanentDeliveryError: If user has no email in credentials.
        """
        email_creds = (user.credentials or {}).get("email")
        if not email_creds or "email" not in email_creds:
            raise PermanentDeliveryError(
                "User has no email credentials (TD-056)"
            )

        recipient = email_creds["email"]
        lang = getattr(user, "language", "en") or "en"
        variables = _build_variables(notification)

        subject = render(
            notification_type=notification.type,
            channel="email",
            field="subject",
            lang=lang,
            variables=variables,
        )
        body = render(
            notification_type=notification.type,
            channel="email",
            field="body",
            lang=lang,
            variables=variables,
        )

        # Determine delivery strategy based on recipient domain.
        domain = recipient.rsplit("@", 1)[-1].lower()
        high_secured = settings.high_secured_domain_list

        if domain in high_secured:
            # High-secured domain -> Mailgun only.
            return await self._send_mailgun(recipient, subject, body)

        # Normal domain -> SMTP primary, Mailgun fallback.
        try:
            return await self._send_smtp(recipient, subject, body)
        except Exception as smtp_exc:
            logger.warning(
                "smtp_failed_fallback_mailgun",
                recipient=recipient,
                error=str(smtp_exc)[:200],
            )
            return await self._send_mailgun(recipient, subject, body)

    async def _send_smtp(
        self,
        recipient: str,
        subject: str,
        body: str,
    ) -> bool:
        """Send email via local SMTP (Postfix)."""
        import aiosmtplib

        msg = EmailMessage()
        msg["From"] = self._from_email
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)

        kwargs: dict = {
            "hostname": self._smtp_host,
            "port": self._smtp_port,
        }

        if self._use_tls:
            kwargs["start_tls"] = True

        if self._smtp_user:
            kwargs["username"] = self._smtp_user
            kwargs["password"] = self._smtp_password

        await aiosmtplib.send(msg, **kwargs)

        logger.info("email_sent_smtp", recipient=recipient, subject=subject)
        return True

    async def _send_mailgun(
        self,
        recipient: str,
        subject: str,
        body: str,
    ) -> bool:
        """Send email via Mailgun HTTP API."""
        import httpx

        if not self._mailgun_api_key or self._mailgun_api_key == "TEST":
            logger.error("mailgun_not_configured")
            return False

        url = f"https://api.mailgun.net/v3/{self._mailgun_domain}/messages"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                auth=("api", self._mailgun_api_key),
                data={
                    "from": self._from_email,
                    "to": [recipient],
                    "subject": subject,
                    "text": body,
                },
            )

        if resp.status_code == 200:
            logger.info(
                "email_sent_mailgun",
                recipient=recipient,
                subject=subject,
            )
            return True

        logger.error(
            "mailgun_send_failed",
            status=resp.status_code,
            body=resp.text[:500],
        )
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_variables(notification: Notification) -> dict:
    """Build template variables from notification fields and action_data.

    Merges title, body, and any non-internal keys from action_data.
    """
    variables: dict = {
        "title": notification.title,
        "body": notification.body,
    }
    if notification.action_data:
        for key, value in notification.action_data.items():
            # Skip internal keys (prefixed with underscore).
            if not key.startswith("_"):
                variables[key] = value
    return variables


# ---------------------------------------------------------------------------
# Formatter registry + lazy init
# ---------------------------------------------------------------------------

_stub = StubFormatter()
_initialized = False

_FORMATTERS: dict[str, ChannelFormatter] = {
    DeliveryChannel.TELEGRAM: _stub,
    DeliveryChannel.EMAIL: _stub,
    DeliveryChannel.PUSH: _stub,
    DeliveryChannel.IN_APP: _stub,
}


def _init_formatters() -> None:
    """Initialize real formatters based on config values.

    Called once on first get_formatter() call. Uses StubFormatter
    when credentials are not configured (TEST mode).
    """
    global _initialized

    # -- Telegram --
    token = settings.telegram_bot_token
    if token and token != "TEST":
        try:
            _FORMATTERS[DeliveryChannel.TELEGRAM] = TelegramFormatter(token)
            logger.info("telegram_formatter_initialized")
        except Exception:
            logger.exception("telegram_formatter_init_failed")
    else:
        logger.info("telegram_formatter_stub", reason="token is TEST")

    # -- Email --
    smtp_host = settings.smtp_host
    if smtp_host:
        try:
            _FORMATTERS[DeliveryChannel.EMAIL] = EmailFormatter(
                smtp_host=smtp_host,
                smtp_port=settings.smtp_port,
                smtp_user=settings.smtp_user,
                smtp_password=settings.smtp_password,
                from_email=settings.smtp_from_email,
                use_tls=settings.smtp_use_tls,
                mailgun_api_key=settings.mailgun_api_key,
                mailgun_domain=settings.mailgun_domain,
            )
            logger.info("email_formatter_initialized", smtp_host=smtp_host)
        except Exception:
            logger.exception("email_formatter_init_failed")
    else:
        logger.info("email_formatter_stub", reason="smtp_host is empty")

    _initialized = True


def get_formatter(channel: str) -> ChannelFormatter:
    """Get the formatter for a delivery channel.

    Initializes real formatters on first call (lazy init).
    Falls back to StubFormatter for unknown channels.
    """
    global _initialized
    if not _initialized:
        _init_formatters()
    return _FORMATTERS.get(channel, _stub)
