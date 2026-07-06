"""Email Digest & Alert Sender

Sends transactional alert emails via SMTP (STARTTLS) or SendGrid.

Configuration via environment variables:
  EMAIL_BACKEND       smtp | sendgrid  (default: smtp)
  SMTP_HOST           (default: localhost)
  SMTP_PORT           (default: 587)
  SMTP_USER
  SMTP_PASSWORD
  SMTP_FROM           sender address
  EMAIL_TO            comma-separated recipient list
  SENDGRID_API_KEY    required when EMAIL_BACKEND=sendgrid
"""
from __future__ import annotations

import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_BACKEND = os.getenv("EMAIL_BACKEND", "smtp").lower()
_SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
_SMTP_FROM = os.getenv("SMTP_FROM", "noreply@azure-optimizer")
_EMAIL_TO = [e.strip() for e in os.getenv("EMAIL_TO", "").split(",") if e.strip()]
_SENDGRID_KEY = os.getenv("SENDGRID_API_KEY", "")


async def send_email_alert(
    subject: str,
    body: str,
    recipients: list[str] | None = None,
    html_body: str | None = None,
) -> bool:
    """Send a transactional alert email.

    Returns True on success, False on failure (never raises).
    """
    to = recipients or _EMAIL_TO
    if not to:
        log.debug("email_digest.no_recipients_configured")
        return False

    if _BACKEND == "sendgrid":
        return await _send_sendgrid(subject, body, to, html_body)
    return await _send_smtp(subject, body, to, html_body)


async def _send_smtp(
    subject: str,
    body: str,
    to: list[str],
    html_body: str | None,
) -> bool:
    import asyncio
    import smtplib

    def _send() -> bool:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = _SMTP_FROM
        msg["To"] = ", ".join(to)
        msg.attach(MIMEText(body, "plain"))
        if html_body:
            msg.attach(MIMEText(html_body, "html"))
        try:
            with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls()
                if _SMTP_USER:
                    smtp.login(_SMTP_USER, _SMTP_PASSWORD)
                smtp.sendmail(_SMTP_FROM, to, msg.as_string())
            return True
        except Exception as exc:
            log.warning("email_digest.smtp_failed", error=str(exc))
            return False

    return await asyncio.get_event_loop().run_in_executor(None, _send)


async def _send_sendgrid(
    subject: str,
    body: str,
    to: list[str],
    html_body: str | None,
) -> bool:
    try:
        import httpx
        content = [
            {"type": "text/plain", "value": body},
        ]
        if html_body:
            content.append({"type": "text/html", "value": html_body})
        payload = {
            "personalizations": [{"to": [{"email": addr} for addr in to]}],
            "from": {"email": _SMTP_FROM},
            "subject": subject,
            "content": content,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={
                    "Authorization": f"Bearer {_SENDGRID_KEY}",
                    "Content-Type": "application/json",
                },
            )
            ok = resp.status_code in (200, 202)
            if not ok:
                log.warning(
                    "email_digest.sendgrid_failed",
                    status=resp.status_code,
                    body=resp.text[:200],
                )
            return ok
    except Exception as exc:
        log.warning("email_digest.sendgrid_exception", error=str(exc))
        return False
