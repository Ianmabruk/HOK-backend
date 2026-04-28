"""
HOK Interior Designs — SendGrid Email Service
────────────────────────────────────────────────
All public send_* helpers are non-blocking: they fire a daemon thread so HTTP
responses are never delayed by email delivery.

Usage:
    from services.email_service import send_welcome_email
    send_welcome_email(user.email, user.name, verify_url)
"""

import logging
import os
import re
import threading
from html import escape

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Email, Mail

logger = logging.getLogger(__name__)


# ─── HTML base template ───────────────────────────────────────────────────────

_BASE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#f5f0eb;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
         style="background:#f5f0eb;padding:40px 20px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:600px;width:100%;background:#ffffff;border-radius:3px;
                    box-shadow:0 2px 8px rgba(0,0,0,.06);overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="background:#2c2c2c;padding:26px 40px;text-align:center;">
            <span style="font-family:Georgia,'Times New Roman',serif;font-size:22px;
                         color:#ffffff;letter-spacing:3px;">HOK</span>
            <span style="font-family:Georgia,'Times New Roman',serif;font-size:22px;
                         color:#c25b3f;letter-spacing:3px;"> Interior Designs</span>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:40px 40px 32px;">
            {body}
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f5f0eb;padding:22px 40px;text-align:center;
                     border-top:1px solid #e5ddd4;">
            <p style="margin:0;font-size:12px;color:#9a8a7a;line-height:1.7;">
              HOK Interior Designs &mdash; Timeless spaces, elevated living.<br/>
              You&rsquo;re receiving this because you have an account with us.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _wrap(body: str, subject: str) -> str:
    return _BASE.format(body=body, subject=subject)


def _btn(label: str, url: str) -> str:
    return (
        f'<a href="{url}" target="_blank"'
        f' style="display:inline-block;background:#c25b3f;color:#ffffff;'
        f'text-decoration:none;padding:13px 36px;border-radius:2px;'
        f'font-size:12px;letter-spacing:1.8px;text-transform:uppercase;'
        f'font-weight:600;">{label}</a>'
    )


def _h2(text: str) -> str:
    return (
        f'<h2 style="font-family:Georgia,serif;font-size:24px;color:#2c2c2c;'
        f'margin:0 0 14px;font-weight:normal;">{text}</h2>'
    )


def _p(text: str, muted: bool = False) -> str:
    color = "#9a8a7a" if muted else "#5a5050"
    return (
        f'<p style="font-size:15px;line-height:1.7;color:{color};margin:0 0 18px;">'
        f'{text}</p>'
    )


def _divider() -> str:
    return '<hr style="border:none;border-top:1px solid #e5ddd4;margin:24px 0 20px;"/>'


# ─── Individual email templates ───────────────────────────────────────────────

def _welcome_body(name: str, verify_url: str) -> str:
    return (
        _h2(f"Welcome, {name}!")
        + _p("Thank you for joining HOK Interior Designs. We're excited to help "
             "you discover beautiful furniture and décor for every room.")
        + _p("Please verify your email address to unlock all features:")
        + f'<p style="text-align:center;margin:28px 0;">{_btn("Verify Email Address", verify_url)}</p>'
        + _divider()
        + _p("This link expires in <strong>24 hours</strong>. "
             "If you didn't create an account, you can safely ignore this email.", muted=True)
    )


def _verify_email_body(name: str, verify_url: str) -> str:
    return (
        _h2("Verify your email address")
        + _p(f"Hi {name}, thanks for signing up. Click the button below to confirm your "
             "email address and activate your account.")
        + f'<p style="text-align:center;margin:28px 0;">{_btn("Verify Email Address", verify_url)}</p>'
        + _divider()
        + _p("Link expires in <strong>24 hours</strong>. Didn't sign up? You can ignore this email.", muted=True)
    )


def _reset_password_body(name: str, reset_url: str) -> str:
    return (
        _h2("Reset your password")
        + _p(f"Hi {name},")
        + _p("We received a request to reset your HOK Interior Designs password. "
             "Click the button below to choose a new one:")
        + f'<p style="text-align:center;margin:28px 0;">{_btn("Reset My Password", reset_url)}</p>'
        + _divider()
        + _p(
            "This link expires in <strong>1 hour</strong>. "
            "If you didn't request a password reset, no changes have been made &mdash; "
            "your account is safe.",
            muted=True,
        )
    )


def _login_alert_body(name: str, ip: str, time_str: str, change_url: str) -> str:
    info_box = (
        '<table cellpadding="0" cellspacing="0" role="presentation" width="100%"'
        ' style="background:#f5f0eb;border-radius:3px;padding:16px 20px;margin-bottom:24px;">'
        f'<tr><td style="font-size:13px;color:#5a5050;padding:3px 0;">'
        f'<strong style="color:#2c2c2c;">IP&nbsp;Address:</strong>&nbsp;{ip}</td></tr>'
        f'<tr><td style="font-size:13px;color:#5a5050;padding:3px 0;">'
        f'<strong style="color:#2c2c2c;">Time:</strong>&nbsp;{time_str}</td></tr>'
        '</table>'
    )
    return (
        _h2("New sign-in detected")
        + _p(f"Hi {name}, we noticed a sign-in to your account from a <strong>new location</strong>.")
        + info_box
        + _p("If this was you, no action is needed. If you don't recognise this activity, "
             "change your password immediately:")
        + f'<p style="text-align:center;margin:28px 0;">{_btn("Change My Password", change_url)}</p>'
    )


def _password_changed_body(name: str) -> str:
    return (
        _h2("Your password was changed")
        + _p(f"Hi {name}, your HOK Interior Designs account password was successfully updated.")
        + _p("If you made this change, no further action is needed.")
        + _divider()
        + _p(
            "If you didn't change your password, please contact us immediately "
            "by replying to this email.",
            muted=True,
        )
    )


# ─── Core delivery engine ─────────────────────────────────────────────────────

def _plain_text_content(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _response_body_text(body) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)

def _deliver(to_email: str, subject: str, html: str) -> None:
    """Synchronous delivery — called from a background thread."""
    api_key = (os.environ.get("SENDGRID_API_KEY") or "").strip()
    if not api_key:
        logger.error("[email] SENDGRID_API_KEY not set — email to %s skipped", to_email)
        return

    from_addr = (os.environ.get("FROM_EMAIL") or os.environ.get("SENDGRID_FROM_EMAIL") or "").strip()
    if not from_addr:
        logger.error("[email] FROM_EMAIL not set — email to %s skipped", to_email)
        return

    from_name = (os.environ.get("EMAIL_FROM_NAME") or "HOK Interior Designs").strip() or "HOK Interior Designs"

    message = Mail(
        from_email=Email(from_addr, from_name),
        to_emails=to_email,
        subject=subject,
        html_content=html,
        plain_text_content=_plain_text_content(html),
    )

    try:
        sg = SendGridAPIClient(api_key)
        resp = sg.send(message)
        status_code = int(getattr(resp, "status_code", 0) or 0)
        if 200 <= status_code < 300:
            logger.info("[email] Sent '%s' → %s  (status %s)", subject, to_email, status_code)
            return

        logger.error(
            "[email] SendGrid rejected '%s' → %s (status %s, body=%s)",
            subject,
            to_email,
            status_code,
            _response_body_text(getattr(resp, "body", ""))[:500],
        )
    except Exception as exc:
        logger.error("[email] Failed to send '%s' → %s: %s", subject, to_email, exc)


def send_email(to_email: str, subject: str, html: str) -> None:
    """Non-blocking: spawn a daemon thread for delivery so HTTP responses never wait."""
    t = threading.Thread(target=_deliver, args=(to_email, subject, html), daemon=True)
    t.start()


# ─── Public send helpers ──────────────────────────────────────────────────────

def send_welcome_email(to_email: str, name: str, verify_url: str) -> None:
    """Sent immediately after account creation."""
    subject = "Welcome to HOK Interior Designs"
    send_email(to_email, subject, _wrap(_welcome_body(name, verify_url), subject))


def send_verify_email(to_email: str, name: str, verify_url: str) -> None:
    """Resend verification link on-demand."""
    subject = "Verify your email — HOK Interior Designs"
    send_email(to_email, subject, _wrap(_verify_email_body(name, verify_url), subject))


def send_reset_email(to_email: str, name: str, reset_url: str) -> None:
    """Password-reset link email."""
    subject = "Reset your password — HOK Interior Designs"
    send_email(to_email, subject, _wrap(_reset_password_body(name, reset_url), subject))


def send_login_alert(to_email: str, name: str, ip: str, time_str: str, change_url: str) -> None:
    """Login from new IP alert — suspicious activity notification."""
    subject = "New sign-in detected — HOK Interior Designs"
    send_email(to_email, subject, _wrap(_login_alert_body(name, ip, time_str, change_url), subject))


def send_password_changed(to_email: str, name: str) -> None:
    """Confirmation email after a successful password reset."""
    subject = "Password updated — HOK Interior Designs"
    send_email(to_email, subject, _wrap(_password_changed_body(name), subject))


def _admin_message_body(name: str, message: str) -> str:
    safe_name = escape(name or 'there')
    paragraphs = [segment.strip() for segment in re.split(r'\n\s*\n', message.strip()) if segment.strip()]
    rendered_message = ''.join(_p(escape(segment).replace('\n', '<br/>')) for segment in paragraphs)
    return (
        _h2('A message from HOK Interior Designs')
        + _p(f'Hi {safe_name},')
        + rendered_message
        + _divider()
        + _p('If you have questions, reply to this email and our team will get back to you.', muted=True)
    )


def send_admin_message(to_email: str, name: str, subject: str, message: str) -> None:
    """Admin-composed message sent to a customer."""
    send_email(to_email, subject, _wrap(_admin_message_body(name, message), subject))
