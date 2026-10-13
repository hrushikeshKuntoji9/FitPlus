"""FitPulse email notifications. SMTP-based; no-ops with a clear status when unconfigured."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Optional, Tuple


def _configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def email_status() -> dict:
    return {
        "configured": _configured(),
        "provider": os.environ.get("EMAIL_PROVIDER", "smtp"),
        "from": os.environ.get("SMTP_FROM_EMAIL") or os.environ.get("SMTP_USER") or "",
    }


def send_email(to_addr: str, subject: str, text_body: str, html_body: Optional[str] = None) -> Tuple[bool, str]:
    """Send an email. Returns (ok, message). Never pretends success if SMTP is unavailable."""
    if not to_addr or "@" not in to_addr:
        return False, "Invalid recipient."
    if not _configured():
        return False, "Email is not configured. Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD."

    from_name = os.environ.get("SMTP_FROM_NAME", "FitPulse")
    from_email = os.environ.get("SMTP_FROM_EMAIL") or os.environ.get("SMTP_USER")
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_addr
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            if port != 25:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(msg)
        return True, "sent"
    except Exception as exc:
        return False, f"Email send failed: {type(exc).__name__}"


def send_password_reset(to_addr: str, reset_url: str) -> Tuple[bool, str]:
    text = (
        "Reset your FitPulse password using this link (valid for 1 hour):\n\n"
        f"{reset_url}\n\nIf you did not request this, you can ignore this email."
    )
    html = f"<p>Reset your FitPulse password (valid for 1 hour):</p><p><a href=\"{reset_url}\">{reset_url}</a></p>"
    return send_email(to_addr, "Reset your FitPulse password", text, html)


def send_verification(to_addr: str, verify_url: str) -> Tuple[bool, str]:
    text = f"Confirm your FitPulse email address:\n\n{verify_url}\n"
    html = f"<p>Confirm your FitPulse email:</p><p><a href=\"{verify_url}\">{verify_url}</a></p>"
    return send_email(to_addr, "Verify your FitPulse email", text, html)


def send_contact_ack(to_addr: str, name: str) -> Tuple[bool, str]:
    text = f"Hi {name},\n\nWe received your message and will reply soon.\n\n— FitPulse"
    return send_email(to_addr, "We received your message — FitPulse", text)


def send_payment_confirmation(to_addr: str, plan_name: str, amount: int, expiry: str, order_id: str) -> Tuple[bool, str]:
    text = (
        f"Your FitPulse {plan_name} membership is active.\n"
        f"Amount: ₹{amount}\nOrder: {order_id}\nAccess until: {expiry}\n"
    )
    return send_email(to_addr, "FitPulse Premium confirmed", text)
