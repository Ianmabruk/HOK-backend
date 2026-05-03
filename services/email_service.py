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
from datetime import datetime
from html import escape

from flask import current_app, has_app_context
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Email, Mail

logger = logging.getLogger(__name__)


def _setting(key: str, *, app=None, default: str = '', aliases: tuple[str, ...] = ()) -> str:
    if app is None and has_app_context():
        app = current_app._get_current_object()

    candidates = (key, *aliases)
    if app is not None:
        for candidate in candidates:
            value = app.config.get(candidate)
            if value is not None and str(value).strip():
                return str(value).strip()

    for candidate in candidates:
        value = os.environ.get(candidate)
        if value is not None and str(value).strip():
            return str(value).strip()

    return default


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


def _login_notice_body(name: str, ip: str, time_str: str, change_url: str, is_new_location: bool = False) -> str:
    info_box = (
        '<table cellpadding="0" cellspacing="0" role="presentation" width="100%"'
        ' style="background:#f5f0eb;border-radius:3px;padding:16px 20px;margin-bottom:24px;">'
        f'<tr><td style="font-size:13px;color:#5a5050;padding:3px 0;">'
        f'<strong style="color:#2c2c2c;">IP&nbsp;Address:</strong>&nbsp;{ip}</td></tr>'
        f'<tr><td style="font-size:13px;color:#5a5050;padding:3px 0;">'
        f'<strong style="color:#2c2c2c;">Time:</strong>&nbsp;{time_str}</td></tr>'
        '</table>'
    )
    heading = 'New sign-in detected' if is_new_location else 'Sign-in successful'
    intro = (
        f"Hi {name}, we noticed a sign-in to your account from a <strong>new location</strong>."
        if is_new_location
        else f'Hi {name}, this is a confirmation that your account was just signed in.'
    )
    action_text = (
        "If this wasn't you, reset your password immediately:"
        if is_new_location
        else "If this wasn't you, please reset your password immediately:"
    )
    return (
        _h2(heading)
        + _p(intro)
        + info_box
        + _p(action_text)
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


def _order_confirmation_body(
    name: str,
    order_id: int,
    total_price: float,
    items: list[dict],
    shipping_info: dict | None = None,
    is_quote_request: bool = False,
    currency_symbol: str = '$',
    currency_code: str = 'USD',
) -> str:
    safe_name = escape(name or 'there')
    shipping_info = shipping_info if isinstance(shipping_info, dict) else {}

    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = escape(str(item.get('product_title') or (item.get('product') or {}).get('title') or 'Product'))
        quantity = int(item.get('quantity') or 0)
        unit_price = float(item.get('unit_price') or ((item.get('product') or {}).get('price') or 0))
        line_total = unit_price * quantity
        lines.append(
            '<tr>'
            f'<td style="padding:8px 0;color:#2c2c2c;font-size:14px;">{title}</td>'
            f'<td style="padding:8px 0;color:#5a5050;font-size:13px;text-align:center;">{quantity}</td>'
            f'<td style="padding:8px 0;color:#2c2c2c;font-size:14px;text-align:right;">{currency_symbol}{line_total:,.2f}</td>'
            '</tr>'
        )

    items_table = (
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        'style="border-collapse:collapse;margin:8px 0 4px;">'
        '<thead>'
        '<tr>'
        '<th style="text-align:left;padding:8px 0;border-bottom:1px solid #e5ddd4;font-size:11px;letter-spacing:1.2px;text-transform:uppercase;color:#9a8a7a;">Item</th>'
        '<th style="text-align:center;padding:8px 0;border-bottom:1px solid #e5ddd4;font-size:11px;letter-spacing:1.2px;text-transform:uppercase;color:#9a8a7a;">Qty</th>'
        '<th style="text-align:right;padding:8px 0;border-bottom:1px solid #e5ddd4;font-size:11px;letter-spacing:1.2px;text-transform:uppercase;color:#9a8a7a;">Total</th>'
        '</tr>'
        '</thead>'
        '<tbody>'
        f"{''.join(lines) if lines else '<tr><td colspan=\"3\" style=\"padding:10px 0;color:#5a5050;\">No line items were recorded.</td></tr>'}"
        '</tbody>'
        '</table>'
    )

    shipping_name = ' '.join([
        str(shipping_info.get('first_name') or '').strip(),
        str(shipping_info.get('last_name') or '').strip(),
    ]).strip() or safe_name
    shipping_city = escape(str(shipping_info.get('city') or '').strip())
    shipping_country = escape(str(shipping_info.get('country') or '').strip())
    shipping_address = escape(str(shipping_info.get('address') or '').strip())

    shipping_block = ''
    if shipping_address or shipping_city or shipping_country:
        location_bits = ', '.join([bit for bit in [shipping_city, shipping_country] if bit])
        shipping_block = (
            _divider()
            + _p('<strong>Shipping to:</strong>')
            + _p(f"{escape(shipping_name)}<br/>{shipping_address}<br/>{location_bits}")
        )

    return (
        _h2('Quote request received' if is_quote_request else 'Order received')
        + _p(
            (
                f'Thank you, {safe_name}. Your quote request <strong>#{order_id}</strong> has been received. '
                'Our team will review it and contact you shortly.'
            )
            if is_quote_request
            else f'Thank you, {safe_name}. Your order <strong>#{order_id}</strong> has been received and is now being processed.'
        )
        + items_table
        + _p(f'<strong>{"Estimated Total" if is_quote_request else "Order Total"}:</strong> {currency_symbol}{float(total_price or 0):,.2f}')
        + shipping_block
        + _divider()
        + _p(
            'We will send another update when your quote is ready.' if is_quote_request
            else 'We will send another update when your order status changes.',
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


def _update_delivery_log(app, delivery_log_id, **fields) -> None:
    if not app or not delivery_log_id:
        return

    from models.models import EmailDeliveryLog, db

    with app.app_context():
        delivery_log = db.session.get(EmailDeliveryLog, delivery_log_id)
        if not delivery_log:
            return
        for key, value in fields.items():
            setattr(delivery_log, key, value)
        db.session.commit()


def sendgrid_health_payload() -> dict:
    api_key = _setting('SENDGRID_API_KEY')
    from_email = _setting('FROM_EMAIL', aliases=('SENDGRID_FROM_EMAIL',))
    from_name = _setting('EMAIL_FROM_NAME', default='HOK Interior Designs')
    missing = []
    if not api_key:
        missing.append('SENDGRID_API_KEY')
    if not from_email:
        missing.append('FROM_EMAIL')

    return {
        'service': 'sendgrid',
        'ready': bool(api_key and from_email),
        'checks': {
            'sendgrid_api_key_configured': bool(api_key),
            'from_email_configured': bool(from_email),
            'email_from_name_configured': bool(from_name),
        },
        'missing': missing,
        'provider': 'sendgrid',
    }


def _deliver(app, to_email: str, subject: str, html: str, delivery_log_id: int | None = None) -> None:
    """Synchronous delivery — called from a background thread."""
    api_key = _setting('SENDGRID_API_KEY', app=app)
    if not api_key:
        logger.error("[email] SENDGRID_API_KEY not set — email to %s skipped", to_email)
        _update_delivery_log(app, delivery_log_id, status='failed', provider='sendgrid', error_message='SENDGRID_API_KEY not set')
        return

    from_addr = _setting('FROM_EMAIL', app=app, aliases=('SENDGRID_FROM_EMAIL',))
    if not from_addr:
        logger.error("[email] FROM_EMAIL not set — email to %s skipped", to_email)
        _update_delivery_log(app, delivery_log_id, status='failed', provider='sendgrid', error_message='FROM_EMAIL not set')
        return

    from_name = _setting('EMAIL_FROM_NAME', app=app, default='HOK Interior Designs')

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
            _update_delivery_log(app, delivery_log_id, status='sent', provider='sendgrid', error_message=None, sent_at=datetime.utcnow())
            return

        error_body = _response_body_text(getattr(resp, "body", ""))[:500]
        logger.error(
            "[email] SendGrid rejected '%s' → %s (status %s, body=%s)",
            subject,
            to_email,
            status_code,
            error_body,
        )
        _update_delivery_log(app, delivery_log_id, status='failed', provider='sendgrid', error_message=f'Status {status_code}: {error_body}')
    except Exception as exc:
        logger.error("[email] Failed to send '%s' → %s: %s", subject, to_email, exc)
        _update_delivery_log(app, delivery_log_id, status='failed', provider='sendgrid', error_message=str(exc))


def send_email(to_email: str, subject: str, html: str, delivery_log_id: int | None = None) -> None:
    """Non-blocking: spawn a daemon thread for delivery so HTTP responses never wait."""
    app = current_app._get_current_object() if has_app_context() else None
    t = threading.Thread(target=_deliver, args=(app, to_email, subject, html, delivery_log_id), daemon=True)
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


def send_login_notice(
    to_email: str,
    name: str,
    ip: str,
    time_str: str,
    change_url: str,
    is_new_location: bool = False,
) -> None:
    """Login activity notification after successful sign-in."""
    subject = "Sign-in activity — HOK Interior Designs"
    send_email(to_email, subject, _wrap(_login_notice_body(name, ip, time_str, change_url, is_new_location=is_new_location), subject))


def send_login_alert(to_email: str, name: str, ip: str, time_str: str, change_url: str) -> None:
    """Backward-compatible alias for login notice calls."""
    send_login_notice(to_email, name, ip, time_str, change_url, is_new_location=True)


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


def send_admin_message(to_email: str, name: str, subject: str, message: str, delivery_log_id: int | None = None) -> None:
    """Admin-composed message sent to a customer."""
    send_email(to_email, subject, _wrap(_admin_message_body(name, message), subject), delivery_log_id=delivery_log_id)


def send_order_confirmation_email(
    to_email: str,
    name: str,
    order_id: int,
    total_price: float,
    items: list[dict],
    shipping_info: dict | None = None,
    is_quote_request: bool = False,
    currency_symbol: str = '$',
    currency_code: str = 'USD',
) -> None:
    """Order confirmation sent immediately after checkout."""
    subject_prefix = 'Quote Request' if is_quote_request else 'Order Confirmation'
    subject = f'{subject_prefix} #{order_id} — HOK Interior Designs'
    body = _order_confirmation_body(
        name,
        order_id,
        total_price,
        items,
        shipping_info=shipping_info,
        is_quote_request=is_quote_request,
        currency_symbol=currency_symbol,
        currency_code=currency_code,
    )
    send_email(to_email, subject, _wrap(body, subject))
