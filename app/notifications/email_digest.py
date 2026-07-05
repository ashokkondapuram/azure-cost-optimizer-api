"""Weekly cost-savings email digest via SMTP or SendGrid.

Configuration (environment variables or DB settings under key ``email``):
    EMAIL_ENABLED          0|1  (default 0)
    EMAIL_PROVIDER         smtp | sendgrid  (default smtp)
    EMAIL_FROM             sender address
    EMAIL_TO               comma-separated recipient list
    SMTP_HOST              SMTP server hostname
    SMTP_PORT              SMTP port (default 587)
    SMTP_USERNAME          SMTP auth username
    SMTP_PASSWORD          SMTP auth password
    SMTP_USE_TLS           0|1 (default 1)
    SENDGRID_API_KEY       SendGrid API key (when provider=sendgrid)
"""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import structlog

log = structlog.get_logger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_email_config() -> dict[str, Any]:
    return {
        "enabled": _env_bool("EMAIL_ENABLED", False),
        "provider": os.getenv("EMAIL_PROVIDER", "smtp").strip().lower(),
        "from_addr": os.getenv("EMAIL_FROM", "").strip(),
        "to_addrs": [
            a.strip() for a in os.getenv("EMAIL_TO", "").split(",") if a.strip()
        ],
        "smtp_host": os.getenv("SMTP_HOST", "").strip(),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_username": os.getenv("SMTP_USERNAME", "").strip(),
        "smtp_password": os.getenv("SMTP_PASSWORD", "").strip(),
        "smtp_use_tls": _env_bool("SMTP_USE_TLS", True),
        "sendgrid_api_key": os.getenv("SENDGRID_API_KEY", "").strip(),
    }


def _build_html_body(period_label: str, findings: list[dict[str, Any]]) -> str:
    total_savings = sum(float(f.get("estimated_savings_usd") or 0) for f in findings)
    top = sorted(findings, key=lambda f: float(f.get("estimated_savings_usd") or 0), reverse=True)[:10]

    rows = ""
    for f in top:
        name = f.get("resource_name") or ""
        rule = f.get("rule_id") or ""
        sev = f.get("severity") or ""
        s = float(f.get("estimated_savings_usd") or 0)
        rows += (
            f"<tr><td>{name}</td><td>{rule}</td>"
            f"<td>{sev}</td><td>${s:,.2f}</td></tr>\n"
        )

    return f"""<html><body>
    <h2>Azure Cost Optimizer — {period_label} Digest</h2>
    <p><strong>{len(findings)}</strong> findings | Potential savings: <strong>${total_savings:,.2f}/mo</strong></p>
    <table border="1" cellpadding="4" cellspacing="0">
      <thead><tr><th>Resource</th><th>Rule</th><th>Severity</th><th>Savings/mo</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </body></html>"""


def _send_smtp(cfg: dict[str, Any], subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = ", ".join(cfg["to_addrs"])
    msg.attach(MIMEText(html_body, "html"))

    server: smtplib.SMTP
    if cfg["smtp_use_tls"]:
        server = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30)
        server.starttls()
    else:
        server = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30)

    try:
        if cfg["smtp_username"]:
            server.login(cfg["smtp_username"], cfg["smtp_password"])
        server.sendmail(cfg["from_addr"], cfg["to_addrs"], msg.as_string())
        log.info("email_digest.sent", provider="smtp", recipients=cfg["to_addrs"])
    finally:
        server.quit()


def _send_sendgrid(cfg: dict[str, Any], subject: str, html_body: str) -> None:
    try:
        import sendgrid  # type: ignore
        from sendgrid.helpers.mail import Mail  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Install sendgrid package: pip install sendgrid") from exc

    client = sendgrid.SendGridAPIClient(api_key=cfg["sendgrid_api_key"])
    for recipient in cfg["to_addrs"]:
        message = Mail(
            from_email=cfg["from_addr"],
            to_emails=recipient,
            subject=subject,
            html_content=html_body,
        )
        response = client.send(message)
        log.info("email_digest.sent", provider="sendgrid", status=response.status_code, to=recipient)


def send_weekly_digest(
    findings: list[dict[str, Any]],
    *,
    period_label: str = "Weekly",
    config: dict[str, Any] | None = None,
) -> bool:
    """Send a cost-savings digest email.

    Returns True on success, False if email is disabled or an error occurs.
    """
    cfg = config or _load_email_config()
    if not cfg.get("enabled"):
        log.debug("email_digest.skipped", reason="EMAIL_ENABLED is false")
        return False
    if not cfg["from_addr"] or not cfg["to_addrs"]:
        log.warning("email_digest.skipped", reason="EMAIL_FROM or EMAIL_TO not configured")
        return False

    subject = f"Azure Cost Optimizer — {period_label} Savings Digest"
    html_body = _build_html_body(period_label, findings)
    try:
        if cfg["provider"] == "sendgrid":
            _send_sendgrid(cfg, subject, html_body)
        else:
            _send_smtp(cfg, subject, html_body)
        return True
    except Exception as exc:
        log.error("email_digest.error", error=str(exc))
        return False
