# =============================================================================
# CBSHOME Backend -- Core Email (Sprint 9.2)
# =============================================================================
#
# Low-level email sending with SMTP (primary) + Mailgun (fallback).
#
# EXTRACTED FROM:
#   notifications/formatters.py (Sprint 8.2) -- EmailFormatter._send_smtp
#   and _send_mailgun moved here for reuse across modules.
#
# API:
#   send_smtp()     -- send EmailMessage via aiosmtplib (explicit config)
#   send_mailgun()  -- send via Mailgun HTTP API (explicit config)
#   build_message() -- construct EmailMessage with optional attachment
#   send_email()    -- convenience: reads settings, handles routing
#   mask_email()    -- mask email for logging
#
# ATTACHMENT SUPPORT:
#   build_message() accepts an optional (filename, data, content_type) tuple.
#   send_mailgun() sends attachment via multipart form files parameter.
#
# USAGE:
#   Certificate service: send_email(recipient, subject, body, attachment=...)
#   EmailFormatter: send_smtp() / send_mailgun() with stored config params
# =============================================================================

from email.message import EmailMessage

import structlog

logger = structlog.get_logger()


def mask_email(email: str) -> str:
    """Mask email for logging: 'user@example.com' -> 'u***@example.com'."""
    if "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 1:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def build_message(
    *,
    from_email: str,
    recipient: str,
    subject: str,
    body: str,
    attachment: tuple[str, bytes, str] | None = None,
) -> EmailMessage:
    """Build an EmailMessage with optional attachment.

    Args:
        from_email: Sender address.
        recipient: Recipient address.
        subject: Email subject line.
        body: Plain text body.
        attachment: Optional (filename, data, content_type) tuple.
            Example: ("certificate.pdf", pdf_bytes, "application/pdf")

    Returns:
        Fully constructed EmailMessage ready for sending.
    """
    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    if attachment is not None:
        filename, data, content_type = attachment
        maintype, _, subtype = content_type.partition("/")
        msg.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype or "octet-stream",
            filename=filename,
        )

    return msg


async def send_smtp(
    msg: EmailMessage,
    *,
    hostname: str,
    port: int,
    use_tls: bool = False,
    username: str = "",
    password: str = "",
) -> None:
    """Send an EmailMessage via SMTP (Postfix).

    Raises on failure -- caller handles fallback.
    """
    import aiosmtplib

    kwargs: dict = {
        "hostname": hostname,
        "port": port,
        "start_tls": use_tls,
    }

    if use_tls:
        # Explicit STARTTLS with certificate validation.
        pass

    if username:
        kwargs["username"] = username
        kwargs["password"] = password

    await aiosmtplib.send(msg, **kwargs)

    logger.info(
        "email_sent_smtp",
        recipient=mask_email(str(msg["To"])),
        subject=msg["Subject"],
    )


async def send_mailgun(
    *,
    from_email: str,
    recipient: str,
    subject: str,
    body: str,
    api_key: str,
    domain: str,
    attachment: tuple[str, bytes, str] | None = None,
) -> bool:
    """Send email via Mailgun HTTP API.

    Supports optional file attachment via multipart form upload.

    Returns True on success, False on failure.
    """
    import httpx

    if not api_key or api_key == "TEST":
        logger.error("mailgun_not_configured")
        return False

    url = f"https://api.mailgun.net/v3/{domain}/messages"

    data = {
        "from": from_email,
        "to": [recipient],
        "subject": subject,
        "text": body,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        if attachment is not None:
            filename, file_data, content_type = attachment
            files = {"attachment": (filename, file_data, content_type)}
            resp = await client.post(
                url,
                auth=("api", api_key),
                data=data,
                files=files,
            )
        else:
            resp = await client.post(
                url,
                auth=("api", api_key),
                data=data,
            )

    if resp.status_code in (200, 202):
        logger.info(
            "email_sent_mailgun",
            recipient=mask_email(recipient),
            subject=subject,
        )
        return True

    logger.error(
        "mailgun_send_failed",
        status=resp.status_code,
        body=resp.text[:500],
    )
    return False


async def send_email(
    *,
    recipient: str,
    subject: str,
    body: str,
    attachment: tuple[str, bytes, str] | None = None,
    force_mailgun: bool = False,
) -> bool:
    """Send email using app settings config.

    Convenience wrapper for non-notification code (certificates, etc.).
    Handles SMTP/Mailgun routing and high-secured domain logic.

    Args:
        recipient: Recipient email address.
        subject: Email subject.
        body: Plain text body.
        attachment: Optional (filename, data, content_type).
        force_mailgun: Skip SMTP, send via Mailgun directly.

    Returns:
        True if sent successfully, False otherwise.
    """
    from app.core.config import settings

    # Check high-secured domains.
    domain = recipient.rsplit("@", 1)[-1].lower()
    high_secured = settings.high_secured_domain_list

    if force_mailgun or domain in high_secured:
        return await send_mailgun(
            from_email=settings.smtp_from_email,
            recipient=recipient,
            subject=subject,
            body=body,
            api_key=settings.mailgun_api_key,
            domain=settings.mailgun_domain,
            attachment=attachment,
        )

    # SMTP primary, Mailgun fallback.
    try:
        msg = build_message(
            from_email=settings.smtp_from_email,
            recipient=recipient,
            subject=subject,
            body=body,
            attachment=attachment,
        )
        await send_smtp(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            use_tls=settings.smtp_use_tls,
            username=settings.smtp_user,
            password=settings.smtp_password,
        )
        return True
    except Exception as smtp_exc:
        logger.warning(
            "smtp_failed_fallback_mailgun",
            recipient=mask_email(recipient),
            error=str(smtp_exc)[:200],
        )
        return await send_mailgun(
            from_email=settings.smtp_from_email,
            recipient=recipient,
            subject=subject,
            body=body,
            api_key=settings.mailgun_api_key,
            domain=settings.mailgun_domain,
            attachment=attachment,
        )
