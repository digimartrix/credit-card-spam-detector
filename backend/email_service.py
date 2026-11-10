"""Email delivery through Gmail SMTP or a Google Apps Script web app."""

from __future__ import annotations

import logging
import json
import os
import smtplib
import ssl
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from email.utils import formataddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


@dataclass
class EmailResult:
    success: bool
    provider: str
    error: str | None = None
    dry_run: bool = False
    skipped: bool = False

    def to_dict(self) -> dict[str, str | bool | None]:
        return asdict(self)


def send_email(
    recipient: str,
    subject: str,
    body: str,
    *,
    force_send: bool = True,
) -> EmailResult:
    """Send a plain-text email using the configured server-side provider."""
    if not force_send:
        logger.info("Email dry-run to %s (%s)", recipient, subject)
        return EmailResult(success=True, provider="dev-console", dry_run=True)

    provider = os.getenv("EMAIL_PROVIDER", "gmail_smtp").strip().lower()
    if provider in {"apps_script", "apps-script", "appscript"}:
        return _send_via_apps_script(recipient, subject, body)
    if provider not in {"gmail_smtp", "gmail-smtp", "gmail"}:
        return EmailResult(
            success=False,
            provider=provider or "unknown",
            error="EMAIL_PROVIDER must be 'apps_script' or 'gmail_smtp'.",
        )

    username = os.getenv("GMAIL_USERNAME", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not username or not app_password:
        return EmailResult(
            success=False,
            provider="gmail-smtp",
            error="GMAIL_USERNAME and GMAIL_APP_PASSWORD must be configured on the server.",
        )

    message = EmailMessage()
    sender_name = os.getenv("EMAIL_FROM_NAME", "EXPayshield").strip() or "EXPayshield"
    message["From"] = formataddr((sender_name, username))
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        return EmailResult(
            success=False,
            provider="gmail-smtp",
            error="SMTP_PORT must be a valid port number.",
        )

    try:
        with smtplib.SMTP(host, port, timeout=8) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(username, app_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("Gmail SMTP delivery failed (%s).", type(exc).__name__)
        return EmailResult(
            success=False,
            provider="gmail-smtp",
            error="Email could not be sent. Check the Gmail address and App Password settings.",
        )

    return EmailResult(success=True, provider="gmail-smtp")


def _send_via_apps_script(recipient: str, subject: str, body: str) -> EmailResult:
    """Ask an authenticated Apps Script web app to send this email."""
    endpoint = os.getenv("APPS_SCRIPT_URL", "").strip()
    secret = os.getenv("APPS_SCRIPT_SECRET", "").strip()
    if not endpoint or not secret:
        return EmailResult(
            success=False,
            provider="apps-script",
            error="APPS_SCRIPT_URL and APPS_SCRIPT_SECRET must be configured on the server.",
        )

    request_body = json.dumps(
        {
            "secret": secret,
            "to": recipient,
            "subject": subject,
            "body": body,
        }
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=12) as response:
            response_body = response.read(4096).decode("utf-8")
        result = json.loads(response_body)
        if not isinstance(result, dict) or result.get("ok") is not True:
            logger.warning("Apps Script email delivery was rejected.")
            return EmailResult(
                success=False,
                provider="apps-script",
                error="Apps Script rejected the email request. Check its deployment and shared secret.",
            )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("Apps Script email delivery failed (%s).", type(exc).__name__)
        return EmailResult(
            success=False,
            provider="apps-script",
            error="Email could not be sent through Apps Script. Check the deployment URL and script settings.",
        )

    return EmailResult(success=True, provider="apps-script")
