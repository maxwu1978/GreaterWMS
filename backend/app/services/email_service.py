"""
Email service — sends transactional emails through a configured HTTP/API provider.
SMTP remains only as a local/manual fallback.
"""

import asyncio
import base64
import logging
import re
import smtplib
from collections.abc import Mapping, Sequence
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr

import httpx

from app.core.config import settings

logger = logging.getLogger("wms.email")
SMTP_TIMEOUT_SECONDS = 15
EMAIL_PROVIDER_TIMEOUT_SECONDS = 15
RESEND_API_URL = "https://api.resend.com/emails"
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
SMTP2GO_API_URL = "https://api.smtp2go.com/v3/email/send"
MAILERSEND_API_URL = "https://api.mailersend.com/v1/email"
POSTMARK_API_URL = "https://api.postmarkapp.com/email"
SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"
PROVIDER_ORDER = (
    "brevo",
    "mailersend",
    "smtp2go",
    "postmark",
    "sendgrid",
    "mailgun",
    "resend",
    "smtp",
)
PROVIDER_TRANSPORTS = {
    "brevo": "http_api",
    "mailersend": "http_api",
    "smtp2go": "http_api",
    "postmark": "http_api",
    "sendgrid": "http_api",
    "mailgun": "http_api",
    "resend": "http_api",
    "smtp": "smtp",
}
PROVIDER_REQUIRED_SETTINGS = {
    "brevo": ("BREVO_API_KEY", "sender"),
    "mailersend": ("MAILERSEND_API_KEY", "sender"),
    "smtp2go": ("SMTP2GO_API_KEY", "sender"),
    "postmark": ("POSTMARK_SERVER_TOKEN", "sender"),
    "sendgrid": ("SENDGRID_API_KEY", "sender"),
    "mailgun": ("MAILGUN_API_KEY", "MAILGUN_DOMAIN", "sender"),
    "resend": ("RESEND_API_KEY", "sender"),
    "smtp": ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "sender"),
}

EmailAttachment = Mapping[str, str]
EmailAttachments = Sequence[EmailAttachment]


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _sender_value(*values: str) -> str:
    for value in values:
        cleaned = _clean(value)
        if cleaned:
            return cleaned
    return ""


def _sender_for_provider(provider: str) -> str:
    default_from = _clean(settings.EMAIL_FROM_EMAIL)
    if provider == "resend":
        return _sender_value(settings.RESEND_FROM_EMAIL, default_from)
    if provider == "brevo":
        return _sender_value(settings.BREVO_FROM_EMAIL, default_from)
    if provider == "smtp2go":
        return _sender_value(settings.SMTP2GO_FROM_EMAIL, default_from)
    if provider == "mailersend":
        return _sender_value(settings.MAILERSEND_FROM_EMAIL, default_from)
    if provider == "postmark":
        return _sender_value(settings.POSTMARK_FROM_EMAIL, default_from)
    if provider == "sendgrid":
        return _sender_value(settings.SENDGRID_FROM_EMAIL, default_from)
    if provider == "mailgun":
        return _sender_value(settings.MAILGUN_FROM_EMAIL, default_from)
    if provider == "smtp":
        return _sender_value(settings.SMTP_FROM_EMAIL, default_from, settings.SMTP_USER)
    return default_from


def _split_sender(sender: str) -> tuple[str | None, str]:
    sender_name, sender_email = parseaddr(sender)
    return (sender_name or None), sender_email or sender


def _attachment_mime_type(attachment: EmailAttachment) -> str:
    value = attachment.get("type", "application/pdf")
    if "/" in value:
        return value
    if value == "pdf":
        return "application/pdf"
    return f"application/{value}"


def _smtp_ready() -> bool:
    return bool(settings.SMTP_USER and settings.SMTP_PASSWORD and settings.SMTP_HOST)


def _provider_ready(provider: str) -> bool:
    if provider == "resend":
        return bool(settings.RESEND_API_KEY and _sender_for_provider(provider))
    if provider == "brevo":
        return bool(settings.BREVO_API_KEY and _sender_for_provider(provider))
    if provider == "smtp2go":
        return bool(settings.SMTP2GO_API_KEY and _sender_for_provider(provider))
    if provider == "mailersend":
        return bool(settings.MAILERSEND_API_KEY and _sender_for_provider(provider))
    if provider == "postmark":
        return bool(settings.POSTMARK_SERVER_TOKEN and _sender_for_provider(provider))
    if provider == "sendgrid":
        return bool(settings.SENDGRID_API_KEY and _sender_for_provider(provider))
    if provider == "mailgun":
        return bool(
            settings.MAILGUN_API_KEY
            and settings.MAILGUN_DOMAIN
            and _sender_for_provider(provider)
        )
    if provider == "smtp":
        return _smtp_ready()
    return False


def _provider_missing_settings(provider: str) -> list[str]:
    missing: list[str] = []
    for name in PROVIDER_REQUIRED_SETTINGS.get(provider, ()):
        if name == "sender":
            if not _sender_for_provider(provider):
                missing.append("sender")
            continue
        if not _clean(str(getattr(settings, name, ""))):
            missing.append(name)
    return missing


def _redact_error_message(error: object, max_length: int = 600) -> str:
    message = str(error or "unknown error")
    replacements = [
        (r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer <redacted>"),
        (r"(api-key|X-Smtp2go-Api-Key|X-Postmark-Server-Token):?\s+[A-Za-z0-9._\-]+", r"\1 <redacted>"),
        (r"(key|token|password|secret)=([^&\s]+)", r"\1=<redacted>"),
        (r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "<redacted-email>"),
    ]
    for pattern, replacement in replacements:
        message = re.sub(pattern, replacement, message, flags=re.IGNORECASE)
    message = re.sub(r"\b[A-Za-z0-9_\-.]{40,}\b", "<redacted-token>", message)
    if len(message) > max_length:
        return f"{message[:max_length].rstrip()}..."
    return message


def _html_to_text(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _delivery_error_message(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        detail = (
            f"{response.status_code} {response.reason_phrase} for {response.request.url}"
        )
        body = response.text.strip()
        if body:
            detail = f"{detail}; response={body}"
        return _redact_error_message(detail)
    return _redact_error_message(exc)


def _select_email_provider() -> str | None:
    providers = _provider_candidates()
    return providers[0] if providers else None


def _provider_candidates() -> list[str]:
    requested_provider = _clean(settings.EMAIL_PROVIDER).lower() or "auto"
    ready_providers = [provider for provider in PROVIDER_ORDER if _provider_ready(provider)]
    if requested_provider == "auto":
        return ready_providers

    if requested_provider in ready_providers:
        return [requested_provider] + [
            provider for provider in ready_providers if provider != requested_provider
        ]

    if requested_provider:
        logger.warning(
            "Requested email provider %s is not ready; falling back to any configured provider.",
            requested_provider,
        )
    return ready_providers


def email_delivery_enabled() -> bool:
    return _select_email_provider() is not None


def email_provider_status() -> dict:
    requested_provider = _clean(settings.EMAIL_PROVIDER).lower() or "auto"
    selected_provider = _select_email_provider()
    candidates = _provider_candidates()
    requested_provider_supported = (
        requested_provider == "auto" or requested_provider in PROVIDER_ORDER
    )
    requested_provider_ready = (
        requested_provider == "auto"
        or (requested_provider_supported and _provider_ready(requested_provider))
    )
    return {
        "requested_provider": requested_provider,
        "requested_provider_supported": requested_provider_supported,
        "requested_provider_ready": requested_provider_ready,
        "requested_provider_missing": (
            []
            if requested_provider == "auto" or not requested_provider_supported
            else _provider_missing_settings(requested_provider)
        ),
        "selected_provider": selected_provider,
        "configured_candidates": candidates,
        "delivery_enabled": selected_provider is not None,
        "verification_required": bool(settings.EMAIL_VERIFICATION_REQUIRED),
        "providers": [
            {
                "provider": provider,
                "transport": PROVIDER_TRANSPORTS.get(provider, "unknown"),
                "ready": _provider_ready(provider),
                "selected": provider == selected_provider,
                "configured_candidate": provider in candidates,
                "missing": _provider_missing_settings(provider),
            }
            for provider in PROVIDER_ORDER
        ],
    }


async def send_email_provider_diagnostic(to_email: str) -> dict:
    """
    Send one test email through the configured provider chain.

    The return value is safe for operational diagnostics: it includes provider
    names and redacted errors, but never API keys, passwords, or sender values.
    """
    providers = _provider_candidates()
    status = email_provider_status()
    if not providers:
        return {
            "success": False,
            "selected_provider": None,
            "attempts": [],
            "status": status,
            "message": "No configured email provider is ready.",
        }

    subject = "WMS QuickStart mail provider diagnostic"
    html = """
    <div style="font-family: Arial, sans-serif; max-width: 560px;">
      <h2 style="margin:0 0 12px;color:#13212c;">Mail provider diagnostic</h2>
      <p style="line-height:1.6;color:#334155;">
        This message confirms that the configured WMS QuickStart transactional
        email provider can send from the live environment.
      </p>
    </div>
    """
    attempts: list[dict] = []
    for provider in providers:
        result = await _send_email_with_provider(
            provider=provider,
            to_email=to_email,
            subject=subject,
            html=html,
        )
        attempt = {
            "provider": provider,
            "success": bool(result.get("success")),
        }
        if not result.get("success"):
            attempt["error"] = _redact_error_message(result.get("error", "unknown error"))
        attempts.append(attempt)
        if result.get("success"):
            return {
                "success": True,
                "selected_provider": providers[0],
                "delivered_by": provider,
                "attempts": attempts,
                "status": status,
                "message": f"Diagnostic email sent by {provider}.",
            }

    return {
        "success": False,
        "selected_provider": providers[0],
        "delivered_by": None,
        "attempts": attempts,
        "status": status,
        "message": "All configured email providers failed.",
    }


async def _send_via_resend(
    *,
    to_email: str,
    subject: str,
    html: str,
    attachments: EmailAttachments | None = None,
) -> dict:
    payload: dict = {
        "from": _sender_for_provider("resend"),
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    if attachments:
        payload["attachments"] = attachments

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=EMAIL_PROVIDER_TIMEOUT_SECONDS) as client:
            response = await client.post(RESEND_API_URL, json=payload, headers=headers)
            response.raise_for_status()
        return {"success": True}
    except Exception as e:
        error = _delivery_error_message(e)
        logger.error("Failed to send email via Resend: %s", error)
        return {"success": False, "error": error}


async def _send_via_brevo(
    *,
    to_email: str,
    subject: str,
    html: str,
    attachments: EmailAttachments | None = None,
) -> dict:
    sender_name, sender_email = _split_sender(_sender_for_provider("brevo"))
    sender = {"email": sender_email}
    if sender_name:
        sender["name"] = sender_name

    payload: dict = {
        "sender": sender,
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html,
    }
    if attachments:
        payload["attachment"] = [
            {
                "name": attachment["filename"],
                "content": attachment["content"],
            }
            for attachment in attachments
        ]

    headers = {
        "api-key": settings.BREVO_API_KEY,
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=EMAIL_PROVIDER_TIMEOUT_SECONDS) as client:
            response = await client.post(BREVO_API_URL, json=payload, headers=headers)
            response.raise_for_status()
        return {"success": True}
    except Exception as e:
        error = _delivery_error_message(e)
        logger.error("Failed to send email via Brevo: %s", error)
        return {"success": False, "error": error}


async def _send_via_smtp2go(
    *,
    to_email: str,
    subject: str,
    html: str,
    attachments: EmailAttachments | None = None,
) -> dict:
    payload: dict = {
        "sender": _sender_for_provider("smtp2go"),
        "to": [to_email],
        "subject": subject,
        "html_body": html,
    }
    if attachments:
        payload["attachments"] = [
            {
                "filename": attachment["filename"],
                "fileblob": attachment["content"],
                "mimetype": _attachment_mime_type(attachment),
            }
            for attachment in attachments
        ]

    headers = {
        "X-Smtp2go-Api-Key": settings.SMTP2GO_API_KEY,
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=EMAIL_PROVIDER_TIMEOUT_SECONDS) as client:
            response = await client.post(SMTP2GO_API_URL, json=payload, headers=headers)
            response.raise_for_status()
        return {"success": True}
    except Exception as e:
        error = _delivery_error_message(e)
        logger.error("Failed to send email via SMTP2GO: %s", error)
        return {"success": False, "error": error}


async def _send_via_mailersend(
    *,
    to_email: str,
    subject: str,
    html: str,
    attachments: EmailAttachments | None = None,
) -> dict:
    sender_name, sender_email = _split_sender(_sender_for_provider("mailersend"))
    sender = {"email": sender_email}
    if sender_name:
        sender["name"] = sender_name

    payload: dict = {
        "from": sender,
        "to": [{"email": to_email}],
        "subject": subject,
        "html": html,
        "text": _html_to_text(html),
    }
    if attachments:
        payload["attachments"] = [
            {
                "content": attachment["content"],
                "disposition": "attachment",
                "filename": attachment["filename"],
            }
            for attachment in attachments
        ]

    headers = {
        "Authorization": f"Bearer {settings.MAILERSEND_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=EMAIL_PROVIDER_TIMEOUT_SECONDS) as client:
            response = await client.post(MAILERSEND_API_URL, json=payload, headers=headers)
            response.raise_for_status()
        return {"success": True}
    except Exception as e:
        error = _delivery_error_message(e)
        logger.error("Failed to send email via MailerSend: %s", error)
        return {"success": False, "error": error}


async def _send_via_postmark(
    *,
    to_email: str,
    subject: str,
    html: str,
    attachments: EmailAttachments | None = None,
) -> dict:
    payload: dict = {
        "From": _sender_for_provider("postmark"),
        "To": to_email,
        "Subject": subject,
        "HtmlBody": html,
        "MessageStream": settings.POSTMARK_MESSAGE_STREAM,
    }
    if attachments:
        payload["Attachments"] = [
            {
                "Name": attachment["filename"],
                "Content": attachment["content"],
                "ContentType": _attachment_mime_type(attachment),
            }
            for attachment in attachments
        ]

    headers = {
        "X-Postmark-Server-Token": settings.POSTMARK_SERVER_TOKEN,
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=EMAIL_PROVIDER_TIMEOUT_SECONDS) as client:
            response = await client.post(POSTMARK_API_URL, json=payload, headers=headers)
            response.raise_for_status()
        return {"success": True}
    except Exception as e:
        error = _delivery_error_message(e)
        logger.error("Failed to send email via Postmark: %s", error)
        return {"success": False, "error": error}


async def _send_via_sendgrid(
    *,
    to_email: str,
    subject: str,
    html: str,
    attachments: EmailAttachments | None = None,
) -> dict:
    sender_name, sender_email = _split_sender(_sender_for_provider("sendgrid"))
    sender = {"email": sender_email}
    if sender_name:
        sender["name"] = sender_name

    payload: dict = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": sender,
        "subject": subject,
        "content": [{"type": "text/html", "value": html}],
    }
    if attachments:
        payload["attachments"] = [
            {
                "content": attachment["content"],
                "filename": attachment["filename"],
                "type": _attachment_mime_type(attachment),
                "disposition": "attachment",
            }
            for attachment in attachments
        ]

    headers = {
        "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=EMAIL_PROVIDER_TIMEOUT_SECONDS) as client:
            response = await client.post(SENDGRID_API_URL, json=payload, headers=headers)
            response.raise_for_status()
        return {"success": True}
    except Exception as e:
        error = _delivery_error_message(e)
        logger.error("Failed to send email via SendGrid: %s", error)
        return {"success": False, "error": error}


async def _send_via_mailgun(
    *,
    to_email: str,
    subject: str,
    html: str,
    attachments: EmailAttachments | None = None,
) -> dict:
    base_url = settings.MAILGUN_API_BASE_URL.rstrip("/")
    url = f"{base_url}/v3/{settings.MAILGUN_DOMAIN}/messages"
    data = {
        "from": _sender_for_provider("mailgun"),
        "to": to_email,
        "subject": subject,
        "html": html,
    }
    files = [
        (
            "attachment",
            (
                attachment["filename"],
                base64.b64decode(attachment["content"]),
                _attachment_mime_type(attachment),
            ),
        )
        for attachment in attachments or []
    ]

    try:
        async with httpx.AsyncClient(timeout=EMAIL_PROVIDER_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                data=data,
                files=files or None,
                auth=("api", settings.MAILGUN_API_KEY),
            )
            response.raise_for_status()
        return {"success": True}
    except Exception as e:
        error = _delivery_error_message(e)
        logger.error("Failed to send email via Mailgun: %s", error)
        return {"success": False, "error": error}


def _build_mime_message(
    *,
    from_email: str,
    to_email: str,
    subject: str,
    html: str,
    attachments: EmailAttachments | None = None,
) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html"))

    for attachment in attachments or []:
        part = MIMEApplication(
            base64.b64decode(attachment["content"]),
            _subtype=_attachment_mime_type(attachment).split("/", 1)[-1],
        )
        part.add_header("Content-Disposition", "attachment", filename=attachment["filename"])
        msg.attach(part)

    return msg


def _deliver_message(msg: MIMEMultipart, smtp_user: str, smtp_password: str) -> dict:
    try:
        with smtplib.SMTP_SSL(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
        ) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return {"success": True}
    except Exception as e:
        error = _delivery_error_message(e)
        logger.error("Failed to send email via SMTP: %s", error)
        return {"success": False, "error": error}


async def _send_email(
    *,
    to_email: str,
    subject: str,
    html: str,
    attachments: EmailAttachments | None = None,
) -> dict:
    providers = _provider_candidates()
    if not providers:
        return {"success": False, "error": "No email provider configured"}

    failures: list[str] = []
    for provider in providers:
        result = await _send_email_with_provider(
            provider=provider,
            to_email=to_email,
            subject=subject,
            html=html,
            attachments=attachments,
        )
        if result.get("success"):
            if failures:
                logger.info("Email sent via fallback provider %s", provider)
            return result
        failures.append(f"{provider}: {result.get('error', 'unknown error')}")
        logger.warning("Email provider %s failed; trying fallback if configured.", provider)

    return {"success": False, "error": "; ".join(failures) or "Email delivery failed"}


async def _send_email_with_provider(
    *,
    provider: str,
    to_email: str,
    subject: str,
    html: str,
    attachments: EmailAttachments | None = None,
) -> dict:
    if provider == "brevo":
        return await _send_via_brevo(
            to_email=to_email,
            subject=subject,
            html=html,
            attachments=attachments,
        )

    if provider == "smtp2go":
        return await _send_via_smtp2go(
            to_email=to_email,
            subject=subject,
            html=html,
            attachments=attachments,
        )

    if provider == "mailersend":
        return await _send_via_mailersend(
            to_email=to_email,
            subject=subject,
            html=html,
            attachments=attachments,
        )

    if provider == "postmark":
        return await _send_via_postmark(
            to_email=to_email,
            subject=subject,
            html=html,
            attachments=attachments,
        )

    if provider == "sendgrid":
        return await _send_via_sendgrid(
            to_email=to_email,
            subject=subject,
            html=html,
            attachments=attachments,
        )

    if provider == "mailgun":
        return await _send_via_mailgun(
            to_email=to_email,
            subject=subject,
            html=html,
            attachments=attachments,
        )

    if provider == "resend":
        return await _send_via_resend(
            to_email=to_email,
            subject=subject,
            html=html,
            attachments=attachments,
        )

    if provider == "smtp":
        msg = _build_mime_message(
            from_email=_sender_for_provider("smtp"),
            to_email=to_email,
            subject=subject,
            html=html,
            attachments=attachments,
        )
        return await asyncio.to_thread(
            _deliver_message, msg, settings.SMTP_USER, settings.SMTP_PASSWORD
        )

    return {"success": False, "error": f"Unsupported email provider: {provider}"}


async def send_verification_email(
    to_email: str,
    company_name: str,
    verification_url: str,
):
    """Send a simple email verification link for self-service registrations."""
    subject = f"Verify your email for {company_name}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px;">
      <div style="background: #13212c; color: white; padding: 24px; border-radius: 12px 12px 0 0;">
        <h2 style="margin: 0;">Verify your email</h2>
        <p style="opacity: 0.85; margin: 8px 0 0;">WMS QuickStart registration</p>
      </div>
      <div style="background: #f8fafc; padding: 24px; border: 1px solid #e2e8f0; border-top: none;">
        <p style="font-size: 14px; line-height: 1.7; color: #334155;">
          Thanks for starting a trial for <strong>{company_name}</strong>. Please verify this email
          address before signing in.
        </p>
        <p style="margin: 24px 0;">
          <a href="{verification_url}" style="background: #f7bf45; color: #13212c; padding: 12px 20px; border-radius: 999px; text-decoration: none; font-weight: bold;">
            Verify email
          </a>
        </p>
        <p style="font-size: 12px; line-height: 1.6; color: #64748b;">
          If you did not start this registration, you can ignore this email.
        </p>
      </div>
    </div>
    """

    result = await _send_email(to_email=to_email, subject=subject, html=html)
    if result.get("success"):
        logger.info(f"Verification email sent to {to_email}")
    return result


async def send_password_reset_email(
    to_email: str,
    company_name: str,
    reset_url: str,
):
    """Send a self-service password reset link."""
    subject = f"Reset your password for {company_name}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px;">
      <div style="background: #13212c; color: white; padding: 24px; border-radius: 12px 12px 0 0;">
        <h2 style="margin: 0;">Reset your password</h2>
        <p style="opacity: 0.85; margin: 8px 0 0;">WMS QuickStart account recovery</p>
      </div>
      <div style="background: #f8fafc; padding: 24px; border: 1px solid #e2e8f0; border-top: none;">
        <p style="font-size: 14px; line-height: 1.7; color: #334155;">
          We received a request to reset the password for <strong>{to_email}</strong> in
          <strong>{company_name}</strong>.
        </p>
        <p style="font-size: 14px; line-height: 1.7; color: #334155;">
          Use the secure link below to choose a new password. For security, this link expires in 60 minutes.
        </p>
        <p style="margin: 24px 0;">
          <a href="{reset_url}" style="background: #f7bf45; color: #13212c; padding: 12px 20px; border-radius: 999px; text-decoration: none; font-weight: bold;">
            Reset password
          </a>
        </p>
        <p style="font-size: 12px; line-height: 1.6; color: #64748b;">
          If you did not request a password reset, you can ignore this email and your current password will keep working.
        </p>
      </div>
    </div>
    """

    result = await _send_email(to_email=to_email, subject=subject, html=html)
    if result.get("success"):
        logger.info(f"Password reset email sent to {to_email}")
    return result


async def send_survey_email(
    to_email: str,
    company_name: str,
    contact_name: str,
    contact_email: str,
    summary: str,
    pdf_base64: str,
):
    """
    Send survey assessment email with PDF attachment.
    """
    subject = f"WMS Assessment: {company_name} — {contact_name}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px;">
      <div style="background: linear-gradient(135deg, #1e40af, #3b82f6); color: white; padding: 24px; border-radius: 12px 12px 0 0;">
        <h2 style="margin: 0;">New WMS Assessment Received</h2>
        <p style="opacity: 0.8; margin: 8px 0 0;">GreenEcoPower Corp — WMS QuickStart</p>
      </div>
      <div style="background: #f8fafc; padding: 24px; border: 1px solid #e2e8f0; border-top: none;">
        <h3 style="color: #1e40af; margin-top: 0;">Contact Info</h3>
        <table style="width: 100%; font-size: 14px;">
          <tr><td style="padding: 4px 0; color: #64748b; width: 120px;">Company</td><td><strong>{company_name}</strong></td></tr>
          <tr><td style="padding: 4px 0; color: #64748b;">Contact</td><td>{contact_name}</td></tr>
          <tr><td style="padding: 4px 0; color: #64748b;">Email</td><td><a href="mailto:{contact_email}">{contact_email}</a></td></tr>
        </table>

        <h3 style="color: #1e40af; margin-top: 20px;">Assessment Summary</h3>
        <pre style="background: white; padding: 16px; border-radius: 8px; border: 1px solid #e2e8f0; font-size: 13px; white-space: pre-wrap; line-height: 1.6;">{summary}</pre>

        <p style="margin-top: 20px; padding: 12px; background: #eff6ff; border-radius: 8px; font-size: 13px; color: #1e40af;">
          PDF report attached. Review and follow up within 2 business days.
        </p>
      </div>
      <div style="text-align: center; padding: 16px; font-size: 11px; color: #94a3b8;">
        WMS QuickStart | GreenEcoPower Corp | Mansfield, TX
      </div>
    </div>
    """

    attachments = []
    if pdf_base64:
        attachments.append(
            {
                "filename": f"WMS-Assessment-{company_name.replace(' ', '-')}.pdf",
                "content": pdf_base64,
                "type": "pdf",
            }
        )

    result = await _send_email(
        to_email=to_email,
        subject=subject,
        html=html,
        attachments=attachments,
    )
    if result.get("success"):
        logger.info(f"Survey email sent to {to_email} for {company_name}")
    return result
