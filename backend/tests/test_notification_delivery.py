# =============================================================================
# CBSHOME Backend -- Notification Delivery Tests (Sprint 8.2)
# =============================================================================
#
# Tests cover:
#   1:  SafeDict -- missing key returns "{key}"
#   2:  load_templates -- loads en.yaml successfully
#   3:  render -- variable substitution works
#   4:  render -- language fallback to "en"
#   5:  reload_templates -- clears cache
#   6:  TelegramFormatter -- success (mock bot)
#   7:  TelegramFormatter -- permanent failure (bot blocked)
#   8:  TelegramFormatter -- no telegram credentials
#   9:  EmailFormatter -- SMTP success (mock aiosmtplib)
#   10: EmailFormatter -- SMTP fail -> Mailgun fallback
#   11: EmailFormatter -- high_secured_domain -> Mailgun direct
#   12: EmailFormatter -- no email credentials
#   13: Staff reload endpoint -- 204 with translation_edit
#   14: Staff reload endpoint -- 403 without translation_edit
#   15: deliver_notification -- batch user load + delivery
#   16: deliver_notification -- permanent failure, attempts stay 0
#   17: deliver_notification -- timeout, attempts incremented
#   18: deliver_notification -- user not found, delivery failed
#
# Email prefix: "s82d_" -- unique to this test file.
# =============================================================================

from collections.abc import AsyncGenerator
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.constants import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationStatus,
    NotificationType,
    TargetType,
)
from app.modules.notifications.formatters import (
    EmailFormatter,
    PermanentDeliveryError,
    StubFormatter,
    TelegramFormatter,
)
from app.modules.notifications.models import Notification, NotificationDelivery
from app.modules.notifications.service import (
    create_notification,
    deliver_notification,
    resolve_notification,
)
from app.modules.notifications.template_engine import (
    SafeDict,
    load_templates,
    reload_templates,
    render,
)
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    create_staff_user,
    register_user,
)

EMAIL_PREFIX = "s82d_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users and notifications before and after each test."""
    await _cleanup_notifications(db_session)
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await _cleanup_notifications(db_session)
    await cleanup_test_users(db_session, EMAIL_PREFIX)


async def _cleanup_notifications(session: AsyncSession) -> None:
    """Delete all test notifications (by title prefix)."""
    stmt = select(Notification.id).where(
        Notification.title.startswith("Test:")
    )
    result = await session.execute(stmt)
    notif_ids = [row[0] for row in result.all()]

    if notif_ids:
        await session.execute(
            delete(NotificationDelivery).where(
                NotificationDelivery.notification_id.in_(notif_ids)
            )
        )
        await session.execute(
            delete(Notification).where(Notification.id.in_(notif_ids))
        )
        await session.commit()


def _make_user_stub(
    *,
    user_id: UUID | None = None,
    email: str | None = None,
    telegram_id: int | None = None,
    language: str = "en",
) -> User:
    """Create a minimal User-like object for formatter unit tests.

    Does NOT touch the database. Uses MagicMock with spec=User
    to satisfy the formatter interface.
    """
    user = MagicMock(spec=User)
    user.id = user_id or UUID("00000000-0000-0000-0000-000000000001")
    user.language = language

    credentials: dict = {}
    if email:
        credentials["email"] = {"email": email}
    if telegram_id:
        credentials["telegram"] = {"id": telegram_id}
    user.credentials = credentials

    return user


def _make_notification_stub(
    *,
    title: str = "Test: hello",
    body: str = "Hello world",
    notif_type: str = "system",
) -> Notification:
    """Create a minimal Notification-like object for formatter unit tests."""
    notif = MagicMock(spec=Notification)
    notif.id = UUID("00000000-0000-0000-0000-000000000002")
    notif.title = title
    notif.body = body
    notif.type = notif_type
    notif.action_data = {}
    return notif


def _make_delivery_stub(
    *,
    channel: str = "telegram",
    user_id: UUID | None = None,
) -> NotificationDelivery:
    """Create a minimal NotificationDelivery-like object."""
    delivery = MagicMock(spec=NotificationDelivery)
    delivery.id = UUID("00000000-0000-0000-0000-000000000003")
    delivery.user_id = user_id or UUID("00000000-0000-0000-0000-000000000001")
    delivery.channel = channel
    delivery.channel_options = None
    return delivery


# ===========================================================================
# Template Engine Tests (1-5)
# ===========================================================================


@pytest.mark.asyncio
async def test_safe_dict_missing_key(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SafeDict returns '{key}' for missing keys."""
    d = SafeDict({"name": "Alice"})
    result = "Hello {name}, your {role}".format_map(d)
    assert result == "Hello Alice, your {role}"


@pytest.mark.asyncio
async def test_load_templates(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """load_templates('en') loads YAML and returns nested dict."""
    reload_templates()
    templates = load_templates("en")
    assert "system" in templates
    assert "telegram" in templates["system"]
    assert "body" in templates["system"]["telegram"]


@pytest.mark.asyncio
async def test_render_with_variables(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """render() substitutes variables in template."""
    reload_templates()
    result = render(
        notification_type="transaction",
        channel="email",
        field="subject",
        lang="en",
        variables={"title": "Payment received"},
    )
    assert "Payment received" in result


@pytest.mark.asyncio
async def test_render_language_fallback(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """render() falls back to 'en' when requested language not found."""
    reload_templates()
    result = render(
        notification_type="system",
        channel="telegram",
        field="body",
        lang="xx",
        variables={"title": "Alert", "body": "Something happened"},
    )
    # Should render English template, not raw fallback.
    assert "Alert" in result
    assert "system.telegram.body" not in result


@pytest.mark.asyncio
async def test_reload_templates_clears_cache(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """reload_templates() clears cache so next load reads from disk."""
    load_templates("en")
    reload_templates()
    # After reload, cache is empty -- next load should re-read.
    # We verify by loading again (no error, data present).
    templates = load_templates("en")
    assert "system" in templates


# ===========================================================================
# TelegramFormatter Tests (6-8)
# ===========================================================================


@pytest.mark.asyncio
async def test_telegram_formatter_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """TelegramFormatter sends message via bot.send_message."""
    with patch("app.modules.notifications.formatters.render", return_value="Hello"):
        formatter = TelegramFormatter.__new__(TelegramFormatter)
        formatter._bot = AsyncMock()
        formatter._bot.send_message = AsyncMock(return_value=True)

        user = _make_user_stub(telegram_id=12345)
        notif = _make_notification_stub()
        delivery = _make_delivery_stub(channel="telegram")

        result = await formatter.deliver(notif, delivery, user)

        assert result is True
        formatter._bot.send_message.assert_called_once()
        call_kwargs = formatter._bot.send_message.call_args
        assert call_kwargs.kwargs["chat_id"] == 12345


@pytest.mark.asyncio
async def test_telegram_formatter_permanent_failure(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """TelegramFormatter raises PermanentDeliveryError on 403 (bot blocked)."""
    with patch("app.modules.notifications.formatters.render", return_value="Hello"):
        formatter = TelegramFormatter.__new__(TelegramFormatter)
        formatter._bot = AsyncMock()
        formatter._bot.send_message = AsyncMock(
            side_effect=Exception("Forbidden: bot was blocked by the user")
        )

        user = _make_user_stub(telegram_id=12345)
        notif = _make_notification_stub()
        delivery = _make_delivery_stub(channel="telegram")

        with pytest.raises(PermanentDeliveryError):
            await formatter.deliver(notif, delivery, user)


@pytest.mark.asyncio
async def test_telegram_formatter_no_credentials(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """TelegramFormatter raises PermanentDeliveryError when no telegram creds."""
    formatter = TelegramFormatter.__new__(TelegramFormatter)
    formatter._bot = AsyncMock()

    user = _make_user_stub()  # No telegram_id.
    notif = _make_notification_stub()
    delivery = _make_delivery_stub(channel="telegram")

    with pytest.raises(PermanentDeliveryError, match="no telegram credentials"):
        await formatter.deliver(notif, delivery, user)


# ===========================================================================
# EmailFormatter Tests (9-12)
# ===========================================================================


@pytest.mark.asyncio
async def test_email_formatter_smtp_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """EmailFormatter sends via SMTP successfully."""
    with patch("app.modules.notifications.formatters.render", return_value="Test"):
        formatter = EmailFormatter(
            smtp_host="localhost",
            smtp_port=25,
            smtp_user="",
            smtp_password="",
            from_email="noreply@mail.cbshome.org",
            use_tls=False,
            mailgun_api_key="TEST",
            mailgun_domain="mail.cbshome.org",
        )

        user = _make_user_stub(email="user@example.com")
        notif = _make_notification_stub()
        delivery = _make_delivery_stub(channel="email")

        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            result = await formatter.deliver(notif, delivery, user)

        assert result is True
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_email_formatter_smtp_fail_mailgun_fallback(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """EmailFormatter falls back to Mailgun when SMTP fails."""
    with patch("app.modules.notifications.formatters.render", return_value="Test"):
        formatter = EmailFormatter(
            smtp_host="localhost",
            smtp_port=25,
            smtp_user="",
            smtp_password="",
            from_email="noreply@mail.cbshome.org",
            use_tls=False,
            mailgun_api_key="real-key",
            mailgun_domain="mail.cbshome.org",
        )

        user = _make_user_stub(email="user@example.com")
        notif = _make_notification_stub()
        delivery = _make_delivery_stub(channel="email")

        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=Exception("SMTP down")),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response),
        ):
            result = await formatter.deliver(notif, delivery, user)

        assert result is True


@pytest.mark.asyncio
async def test_email_formatter_high_secured_domain(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """EmailFormatter sends via Mailgun directly for high-secured domains."""
    with (
        patch("app.modules.notifications.formatters.render", return_value="Test"),
        patch("app.modules.notifications.formatters.settings") as mock_settings,
    ):
        mock_settings.high_secured_domain_list = ["t-online.de", "web.de"]

        formatter = EmailFormatter(
            smtp_host="localhost",
            smtp_port=25,
            smtp_user="",
            smtp_password="",
            from_email="noreply@mail.cbshome.org",
            use_tls=False,
            mailgun_api_key="real-key",
            mailgun_domain="mail.cbshome.org",
        )

        user = _make_user_stub(email="user@t-online.de")
        notif = _make_notification_stub()
        delivery = _make_delivery_stub(channel="email")

        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch("aiosmtplib.send", new_callable=AsyncMock) as mock_smtp,
            patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response),
        ):
            result = await formatter.deliver(notif, delivery, user)

        assert result is True
        # SMTP should NOT be called -- Mailgun directly.
        mock_smtp.assert_not_called()


@pytest.mark.asyncio
async def test_email_formatter_no_credentials(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """EmailFormatter raises PermanentDeliveryError when no email creds."""
    formatter = EmailFormatter(
        smtp_host="localhost",
        smtp_port=25,
        smtp_user="",
        smtp_password="",
        from_email="noreply@mail.cbshome.org",
        use_tls=False,
        mailgun_api_key="TEST",
        mailgun_domain="mail.cbshome.org",
    )

    user = _make_user_stub(telegram_id=12345)  # No email.
    notif = _make_notification_stub()
    delivery = _make_delivery_stub(channel="email")

    with pytest.raises(PermanentDeliveryError, match="no email credentials"):
        await formatter.deliver(notif, delivery, user)


# ===========================================================================
# Staff Endpoint Tests (13-14)
# ===========================================================================


@pytest.mark.asyncio
async def test_staff_reload_templates_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/notifications/templates/reload -> 204 with admin."""
    # Admin has all permissions True, including translation_edit.
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )

    resp = await client.post(
        "/api/v1/staff/notifications/templates/reload",
        headers=auth_headers(token),
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_staff_reload_templates_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/notifications/templates/reload -> 403 without translation_edit."""
    # Default staff has translation_edit=False.
    _, token = await create_staff_user(
        client, db_session, email=f"{EMAIL_PREFIX}staff@example.com"
    )

    resp = await client.post(
        "/api/v1/staff/notifications/templates/reload",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


# ===========================================================================
# Service Integration Tests (15-18)
# ===========================================================================


async def _create_investor(
    client: AsyncClient, suffix: str
) -> tuple[UUID, str]:
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    return UUID(data["user"]["id"]), data["session_token"]


@pytest.mark.asyncio
async def test_deliver_notification_with_user_load(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """deliver_notification batch-loads users and delivers via StubFormatter."""
    user_id, _ = await _create_investor(client, "dlv1")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: delivery integration",
        body="Hello",
        target_type=TargetType.USER,
        target_value=str(user_id),
        channels=[DeliveryChannel.IN_APP],
    )
    await db_session.commit()

    await resolve_notification(db_session, notif)
    await db_session.commit()

    # StubFormatter always succeeds.
    await deliver_notification(db_session, notif)
    await db_session.commit()

    # Check delivery status.
    stmt = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif.id,
    )
    result = await db_session.execute(stmt)
    deliveries = list(result.scalars().all())

    assert len(deliveries) == 1
    assert deliveries[0].status == DeliveryStatus.SENT
    assert deliveries[0].sent_at is not None


@pytest.mark.asyncio
async def test_deliver_permanent_failure_no_attempts_increment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PermanentDeliveryError -> delivery FAILED, attempts stays 0."""
    user_id, _ = await _create_investor(client, "perm1")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: permanent fail",
        body="Hello",
        target_type=TargetType.USER,
        target_value=str(user_id),
        channels=[DeliveryChannel.TELEGRAM],
    )
    await db_session.commit()

    await resolve_notification(db_session, notif)
    await db_session.commit()

    # User registered via email -- no telegram credentials.
    # TelegramFormatter will raise PermanentDeliveryError.
    with patch(
        "app.modules.notifications.service.get_formatter"
    ) as mock_get:
        mock_formatter = AsyncMock()
        mock_formatter.deliver = AsyncMock(
            side_effect=PermanentDeliveryError("No telegram")
        )
        mock_get.return_value = mock_formatter

        await deliver_notification(db_session, notif)
        await db_session.commit()

    stmt = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif.id,
    )
    result = await db_session.execute(stmt)
    delivery = result.scalars().first()

    assert delivery is not None
    assert delivery.status == DeliveryStatus.FAILED
    assert delivery.attempts == 0  # Not incremented for permanent failure.
    assert "No telegram" in (delivery.error_message or "")


@pytest.mark.asyncio
async def test_deliver_timeout_increments_attempts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Timeout -> delivery stays pending, attempts incremented."""
    import asyncio

    user_id, _ = await _create_investor(client, "tout1")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: timeout",
        body="Hello",
        target_type=TargetType.USER,
        target_value=str(user_id),
        channels=[DeliveryChannel.IN_APP],
    )
    await db_session.commit()

    await resolve_notification(db_session, notif)
    await db_session.commit()

    # Mock formatter that hangs forever (will be cancelled by wait_for).
    with patch(
        "app.modules.notifications.service.get_formatter"
    ) as mock_get, patch(
        "app.modules.notifications.service._DELIVER_TIMEOUT_SECONDS", 0.1
    ):
        async def slow_deliver(*args, **kwargs):  # type: ignore[no-untyped-def]
            await asyncio.sleep(10)
            return True

        mock_formatter = MagicMock()
        mock_formatter.deliver = slow_deliver
        mock_get.return_value = mock_formatter

        await deliver_notification(db_session, notif)
        await db_session.commit()

    stmt = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif.id,
    )
    result = await db_session.execute(stmt)
    delivery = result.scalars().first()

    assert delivery is not None
    assert delivery.attempts == 1
    assert "Timeout" in (delivery.error_message or "")


@pytest.mark.asyncio
async def test_deliver_user_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Delivery for deleted user -> FAILED with 'User not found'."""
    user_id, _ = await _create_investor(client, "gone1")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: user gone",
        body="Hello",
        target_type=TargetType.USER,
        target_value=str(user_id),
        channels=[DeliveryChannel.IN_APP],
    )
    await db_session.commit()

    await resolve_notification(db_session, notif)
    await db_session.commit()

    # Delete the user after resolve but before deliver.
    await cleanup_test_users(db_session, EMAIL_PREFIX)

    await deliver_notification(db_session, notif)
    await db_session.commit()

    stmt = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif.id,
    )
    result = await db_session.execute(stmt)
    delivery = result.scalars().first()

    assert delivery is not None
    assert delivery.status == DeliveryStatus.FAILED
    assert "User not found" in (delivery.error_message or "")
