"""Email the studio for new orders and blocked attack-shaped traffic."""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from threading import Lock, Thread

from src.models import Order, format_money

logger = logging.getLogger(__name__)

DEFAULT_NOTIFY_EMAIL = "dimitrioupanagiotis@outlook.com"
DEFAULT_SMTP_HOST = "smtp-mail.outlook.com"
DEFAULT_SHOP_URL = "http://127.0.0.1:8000"
RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_RESEND_FROM = "Print Me Maybe <beth.t@example.com>"

_alert_last: dict[str, float] = {}
_alert_lock = Lock()
_failed_logins: dict[str, list[float]] = {}


def notify_email() -> str:
    return os.environ.get("NOTIFY_EMAIL", DEFAULT_NOTIFY_EMAIL).strip()


def smtp_host() -> str:
    return os.environ.get("SMTP_HOST", DEFAULT_SMTP_HOST).strip()


def smtp_port() -> int:
    raw = os.environ.get("SMTP_PORT", "587").strip()
    try:
        return int(raw)
    except ValueError:
        return 587


def smtp_user() -> str:
    return os.environ.get("SMTP_USER", notify_email()).strip()


def smtp_password() -> str:
    return os.environ.get("SMTP_PASSWORD", "").strip()


def resend_api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "").strip()


def resend_from() -> str:
    return os.environ.get("RESEND_FROM", DEFAULT_RESEND_FROM).strip() or DEFAULT_RESEND_FROM


def shop_url() -> str:
    return os.environ.get("SHOP_URL", DEFAULT_SHOP_URL).rstrip("/")


def shop_name() -> str:
    return os.environ.get("SHOP_NAME", "Print Me Maybe")


def mail_configured() -> bool:
    """True when we have an inbox and a working server mail transport."""
    return bool(notify_email() and (resend_api_key() or smtp_password()))


def mail_not_configured_message() -> str:
    """Explain how to put the Resend key on this Hetzner server."""
    return (
        "This running server has no RESEND_API_KEY, so it cannot send mail. "
        "Create a key on resend.com, then set RESEND_API_KEY in /etc/eshop.env "
        "and run: systemctl restart eshop"
    )


def resend_from_needs_domain() -> bool:
    """True when From is still Resend's shared test address (blocked on many accounts)."""
    from_addr = resend_from().lower()
    return "resend.dev" in from_addr or "@example.com>" in from_addr or from_addr.endswith("@example.com")


def mail_domain_unverified_message() -> str:
    """Resend 403: From domain is not verified. Outlook.com cannot be used as From."""
    return (
        "Resend blocked the send: the From domain is not verified. "
        "You cannot use onrender.com, outlook.com, or "
        "beth.t@example.com. Buy a domain, add it at https://resend.com/domains, "
        "wait until Verified, then set RESEND_FROM in /etc/eshop.env to "
        'Print Me Maybe <orders@your-domain> and run: systemctl restart eshop. See README “Order emails”.'
    )


def reset_alerts() -> None:
    """Clear attack-alert cooldowns (tests)."""
    with _alert_lock:
        _alert_last.clear()
        _failed_logins.clear()


def _alert_cooldown() -> int:
    raw = os.environ.get("ATTACK_ALERT_COOLDOWN", "3600").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 3600


def _alert_allowed(kind: str) -> bool:
    now = time.monotonic()
    with _alert_lock:
        last = _alert_last.get(kind)
        if last is not None and now - last < _alert_cooldown():
            return False
        _alert_last[kind] = now
        return True


def order_email_subject(order: Order) -> str:
    return f"New {shop_name()} order #{order.id} ({order.total_display})"


def order_email_body(order: Order) -> str:
    shipping = (
        "Free" if order.shipping_cents == 0 else format_money(order.shipping_cents)
    )
    method = order.shipping_label or "Shipping"
    lines = [
        f"New order #{order.id} — {shop_name()}",
        "",
        "Customer",
        f"Name: {order.customer_name}",
        f"Email: {order.customer_email}",
        f"Method: {method}",
        "Address:",
        order.shipping_address,
        "",
        "Items",
    ]
    for item in order.items:
        lines.append(
            f"- {item.product_name} × {item.quantity} — {item.line_total_display}"
        )
    pay_line = (
        "Card payment received (Stripe)."
        if order.paid
        else "No payment was collected at checkout."
    )
    lines.extend(
        [
            "",
            f"Subtotal: {format_money(order.subtotal_cents)}",
            f"Shipping: {shipping}",
            f"Total: {order.total_display}",
            "",
            pay_line,
            "",
            "Open in studio:",
            f"{shop_url()}/admin/orders/{order.id}",
            "",
        ]
    )
    return "\n".join(lines)


def build_order_email(order: Order) -> EmailMessage:
    """Plain-text studio alert with Reply-To set to the customer."""
    msg = EmailMessage()
    msg["Subject"] = order_email_subject(order)
    msg["From"] = smtp_user() or notify_email()
    msg["To"] = notify_email()
    msg["Reply-To"] = order.customer_email
    msg.set_content(order_email_body(order))
    return msg


def customer_email_subject(order: Order) -> str:
    return f"{shop_name()} order #{order.id}"


def customer_email_body(order: Order) -> str:
    link = (
        f"{shop_url()}/order/{order.lookup_token}"
        if order.lookup_token
        else shop_url()
    )
    shipping = (
        "Free" if order.shipping_cents == 0 else format_money(order.shipping_cents)
    )
    method = order.shipping_label or "Shipping"
    pay_line = (
        "Card payment received. For custom names, photos, or files, reply or DM Instagram."
        if order.paid
        else "No payment was collected at checkout. For custom names, photos, or files, reply or DM Instagram."
    )
    return "\n".join(
        [
            f"Thank you for your {shop_name()} order #{order.id}.",
            "",
            f"Method: {method}",
            f"Shipping: {shipping}",
            f"Total: {order.total_display}",
            "",
            "View your order:",
            link,
            "",
            pay_line,
            "",
        ]
    )


def build_customer_email(order: Order) -> EmailMessage:
    """Confirmation to the buyer with the unguessable order link."""
    msg = EmailMessage()
    msg["Subject"] = customer_email_subject(order)
    msg["From"] = smtp_user() or resend_from()
    msg["To"] = order.customer_email
    msg.set_content(customer_email_body(order))
    return msg


def _send_via_smtp(msg: EmailMessage) -> None:
    host = smtp_host()
    port = smtp_port()
    user = smtp_user()
    password = smtp_password()
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15, context=context) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
        return
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls(context=context)
        smtp.login(user, password)
        smtp.send_message(msg)


def _send_via_resend(*, subject: str, body: str, to: str, reply_to: str = "") -> None:
    payload = {
        "from": resend_from(),
        "to": [to],
        "subject": subject,
        "text": body,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    req = urllib.request.Request(
        RESEND_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resend_api_key()}",
            "Content-Type": "application/json",
            "User-Agent": "PrintMeMaybeShop/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
            if resp.status >= 400:
                raise RuntimeError(f"Resend HTTP {resp.status}: {raw[:300]!r}")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:500]
        raise RuntimeError(_explain_mail_error(detail, exc.code)) from exc


def _explain_mail_error(detail: bytes | str, status: int | None = None) -> str:
    text = detail.decode("utf-8", errors="replace") if isinstance(detail, bytes) else detail
    message = text
    try:
        parsed = json.loads(text)
        message = str(parsed.get("message") or text)
    except Exception:
        pass
    lower = message.lower()
    if "only send testing emails to your own" in lower:
        return (
            "Resend will only deliver to the email you signed up with until you verify a domain. "
            f"Sign up with {notify_email()}, or set NOTIFY_EMAIL on Render to that Resend account email."
        )
    if "api key is invalid" in lower or "invalid api key" in lower or status == 401:
        return "Resend rejected the API key. Create a new key, paste RESEND_API_KEY on Render, Save, then Manual Deploy."
    if "domain is not verified" in lower or "add and verify your domain" in lower:
        return mail_domain_unverified_message()
    return message[:400]


def send_test_email() -> tuple[bool, str]:
    """Send a one-line test to NOTIFY_EMAIL. Used by studio admin."""
    if not notify_email():
        return False, "NOTIFY_EMAIL is empty."
    if not mail_configured():
        return False, mail_not_configured_message()
    try:
        _deliver_studio(
            subject=f"{shop_name()} test email",
            body=(
                f"This is a test from {shop_name()}.\n\n"
                "If you received this, order alerts are working.\n"
            ),
            name="Studio test",
        )
    except Exception as exc:
        logger.exception("Test email failed")
        return False, str(exc)
    return True, f"Sent a test to {notify_email()}. Check Inbox and Junk."


def _deliver_studio(*, subject: str, body: str, reply_to: str = "", name: str = "") -> None:
    if smtp_password():
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = smtp_user()
        msg["To"] = notify_email()
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
        _send_via_smtp(msg)
        return
    if not resend_api_key():
        raise RuntimeError("Set RESEND_API_KEY in /etc/eshop.env to send mail")
    _send_via_resend(subject=subject, body=body, to=notify_email(), reply_to=reply_to)


def notify_new_order(order: Order) -> bool:
    """Email the studio. Never raises — checkout must still succeed."""
    if not mail_configured():
        logger.warning(
            "Order #%s placed; email skipped (set RESEND_API_KEY in /etc/eshop.env).",
            order.id,
        )
        return False
    try:
        _deliver_studio(
            subject=order_email_subject(order),
            body=order_email_body(order),
            reply_to=order.customer_email,
            name=order.customer_name,
        )
    except Exception:
        logger.exception("Could not email order #%s", order.id)
        return False
    try:
        _deliver_customer(order)
    except Exception:
        logger.exception("Could not email customer for order #%s", order.id)
    logger.info("Order #%s emailed to %s", order.id, notify_email())
    return True


def _deliver_customer(order: Order) -> None:
    if not order.customer_email:
        return
    _deliver_customer_message(
        to=order.customer_email,
        subject=customer_email_subject(order),
        body=customer_email_body(order),
    )


def _deliver_customer_message(*, to: str, subject: str, body: str) -> None:
    cleaned = (to or "").strip()
    if not cleaned:
        return
    if smtp_password():
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = smtp_user() or resend_from()
        msg["To"] = cleaned
        msg.set_content(body)
        _send_via_smtp(msg)
        return
    if not resend_api_key():
        return
    _send_via_resend(subject=subject, body=body, to=cleaned)


def notify_payment_failure(*, session_id: str, customer_email: str, reason: str, refunded: bool) -> None:
    """Alert the studio when a paid Stripe session could not become an order."""
    if not mail_configured():
        logger.error(
            "Paid Stripe session %s failed (%s); mail not configured",
            session_id,
            reason,
        )
        return
    refund_line = (
        "Stripe was asked to refund the payment."
        if refunded
        else "Refund failed or was skipped — check Stripe Dashboard."
    )
    body = (
        f"A card payment completed but the shop could not create the order.\n\n"
        f"Stripe session: {session_id}\n"
        f"Customer: {customer_email or '(unknown)'}\n"
        f"Reason: {reason}\n\n"
        f"{refund_line}\n\n"
        f"Studio: {shop_url()}/admin/orders\n"
    )
    try:
        _deliver_studio(
            subject=f"{shop_name()}: paid checkout failed to create an order",
            body=body,
            reply_to=customer_email,
            name="Checkout failure",
        )
    except Exception:
        logger.exception("Could not email payment-failure alert for %s", session_id)


def cancellation_email_subject(order: Order) -> str:
    return f"{shop_name()} order #{order.id} cancelled"


def cancellation_email_body(order: Order, *, refunded: bool) -> str:
    link = (
        f"{shop_url()}/order/{order.lookup_token}"
        if order.lookup_token
        else shop_url()
    )
    if refunded:
        money = (
            f"The card payment of {order.total_display} has been refunded. "
            "It can take a few business days to appear on your statement."
        )
    else:
        money = "No payment was collected for this order."
    return "\n".join(
        [
            f"Your {shop_name()} order #{order.id} has been cancelled.",
            "",
            f"Total: {order.total_display}",
            "",
            money,
            "",
            "View your order:",
            link,
            "",
            "Questions? Reply to this email.",
            "",
        ]
    )


def _studio_cancellation_body(order: Order, *, refunded: bool) -> str:
    if refunded:
        money = "The card payment was refunded through Stripe."
    elif order.paid:
        money = "Payment still shows as paid — check Stripe Dashboard."
    else:
        money = "No payment was collected."
    return (
        f"You cancelled order #{order.id} for {order.customer_name} ({order.customer_email}).\n\n"
        f"Total: {order.total_display}\n"
        f"{money}\n"
        "The customer was emailed.\n\n"
        f"Studio: {shop_url()}/admin/orders/{order.id}\n"
    )


def notify_order_cancelled(order: Order, *, refunded: bool) -> bool:
    """Email the customer (and studio) after an admin cancel. Never raises."""
    if not mail_configured():
        logger.warning(
            "Order #%s cancelled; email skipped (set RESEND_API_KEY in /etc/eshop.env).",
            order.id,
        )
        return False
    try:
        _deliver_studio(
            subject=cancellation_email_subject(order),
            body=_studio_cancellation_body(order, refunded=refunded),
            reply_to=order.customer_email,
            name=order.customer_name,
        )
    except Exception:
        logger.exception("Could not email studio about cancelled order #%s", order.id)
    try:
        _deliver_customer_message(
            to=order.customer_email,
            subject=cancellation_email_subject(order),
            body=cancellation_email_body(order, refunded=refunded),
        )
    except Exception:
        logger.exception("Could not email customer about cancelled order #%s", order.id)
        return False
    logger.info("Cancellation for order #%s emailed to %s", order.id, order.customer_email)
    return True


def schedule_order_email(order: Order) -> None:
    """Email after checkout without blocking the thank-you page."""
    if os.environ.get("NOTIFY_SYNC", "").lower() in {"1", "true", "yes"}:
        notify_new_order(order)
        return
    Thread(target=notify_new_order, args=(order,), daemon=True, name="order-email").start()


def _attack_copy(kind: str, ip: str) -> tuple[str, str]:
    if kind == "login":
        subject = f"{shop_name()}: blocked studio login attempts"
        body = (
            f"The shop blocked repeated studio login tries from {ip}.\n\n"
            "The visitor is locked out for a few minutes. You do not need to do anything "
            "unless you were logging in from that network — if so, wait and try again.\n\n"
            f"Studio login: {shop_url()}/admin/login\n"
        )
    else:
        subject = f"{shop_name()}: blocked checkout flood"
        body = (
            f"The shop blocked repeated checkout attempts from {ip}.\n\n"
            "No extra orders were created. You do not need to do anything.\n\n"
            f"Studio orders: {shop_url()}/admin/orders\n"
        )
    return subject, body


def notify_attack(kind: str, ip: str) -> bool:
    """Email the studio after blocked login or checkout. At most once per cooldown."""
    if kind not in {"login", "checkout"}:
        return False
    if not mail_configured():
        return False
    if not _alert_allowed(kind):
        return False
    subject, body = _attack_copy(kind, ip or "unknown")
    try:
        _deliver_studio(subject=subject, body=body, name="Shop security")
    except Exception:
        logger.exception("Could not send attack alert (%s)", kind)
        with _alert_lock:
            _alert_last.pop(kind, None)
        return False
    logger.warning("Attack alert emailed (%s) from %s", kind, ip)
    return True


def record_failed_login(ip: str) -> bool:
    """Alert after several failed studio logins from the same visitor."""
    now = time.monotonic()
    window = 900
    threshold = 3
    key = ip or "unknown"
    with _alert_lock:
        stamps = [t for t in _failed_logins.get(key, []) if now - t < window]
        stamps.append(now)
        _failed_logins[key] = stamps
        should_alert = len(stamps) >= threshold
    if should_alert:
        return notify_attack("login", key)
    return False
