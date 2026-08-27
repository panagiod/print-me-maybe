"""Stripe Checkout (hosted). No monthly Stripe fee — only a % on paid cards."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

STRIPE_API = "https://api.stripe.com/v1"
DEFAULT_SHOP_URL = "http://127.0.0.1:8000"


def stripe_secret_key() -> str:
    return os.environ.get("STRIPE_SECRET_KEY", "").strip()


def stripe_webhook_secret() -> str:
    return os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()


def payments_configured() -> bool:
    return bool(stripe_secret_key())


def shop_url() -> str:
    return os.environ.get("SHOP_URL", DEFAULT_SHOP_URL).rstrip("/")


def _stripe_request(method: str, path: str, data: dict[str, str] | None = None) -> dict:
    key = stripe_secret_key()
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY is not set")
    body = urllib.parse.urlencode(data or {}).encode("utf-8") if data else None
    req = urllib.request.Request(
        f"{STRIPE_API}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "PrintMeMaybeShop/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        logger.warning("Stripe HTTP %s: %s", exc.code, detail)
        raise RuntimeError(f"Stripe error ({exc.code}): {detail}") from exc


def cart_snapshot(lines: list) -> str:
    """Compact product_id,qty pairs for Stripe metadata (500-char limit)."""
    return json.dumps([[line.product.id, line.quantity] for line in lines], separators=(",", ":"))


def _shipping_line_name(shipping_method: str, delivery_country: str) -> str:
    if shipping_method == "pickup":
        return "Pick up at studio"
    if delivery_country == "other":
        return "Delivery (outside Cyprus)"
    return "Delivery (Cyprus)"


def create_checkout_session(
    *,
    lines: list,
    total_cents: int,
    customer_name: str,
    customer_email: str,
    shipping_address: str,
    shipping_method: str,
    delivery_country: str,
    shipping_cents: int,
    origin: str,
) -> tuple[str, str]:
    """Return (hosted Checkout URL, session id). Amounts are in EUR cents."""
    base = origin.rstrip("/") or shop_url()
    payload: dict[str, str] = {
        "mode": "payment",
        "success_url": f"{base}/pay/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/checkout",
        "customer_email": customer_email,
        "metadata[customer_name]": customer_name[:500],
        "metadata[customer_email]": customer_email[:200],
        "metadata[shipping_address]": shipping_address[:500],
        "metadata[shipping_method]": shipping_method[:50],
        "metadata[delivery_country]": delivery_country[:50],
        "metadata[shipping_cents]": str(shipping_cents),
        "metadata[total_cents]": str(total_cents),
        "metadata[cart]": cart_snapshot(lines)[:500],
    }
    for index, line in enumerate(lines):
        payload[f"line_items[{index}][quantity]"] = str(line.quantity)
        payload[f"line_items[{index}][price_data][currency]"] = "eur"
        payload[f"line_items[{index}][price_data][unit_amount]"] = str(line.product.price_cents)
        payload[f"line_items[{index}][price_data][product_data][name]"] = line.product.name[:200]
    shipping = total_cents - sum(line.line_total_cents for line in lines)
    if shipping > 0:
        i = len(lines)
        payload[f"line_items[{i}][quantity]"] = "1"
        payload[f"line_items[{i}][price_data][currency]"] = "eur"
        payload[f"line_items[{i}][price_data][unit_amount]"] = str(shipping)
        payload[f"line_items[{i}][price_data][product_data][name]"] = _shipping_line_name(
            shipping_method, delivery_country
        )
    session = _stripe_request("POST", "/checkout/sessions", payload)
    url = session.get("url")
    session_id = str(session.get("id") or "")
    if not url or not session_id:
        raise RuntimeError("Stripe did not return a checkout URL")
    return str(url), session_id


def paid_session(session_id: str) -> dict | None:
    """Return the Stripe session if it is paid; otherwise None."""
    cleaned = (session_id or "").strip()
    if not cleaned.startswith("cs_"):
        return None
    session = _stripe_request("GET", f"/checkout/sessions/{urllib.parse.quote(cleaned)}")
    if session.get("payment_status") != "paid":
        return None
    return session


def verify_webhook_signature(payload: bytes, header: str, secret: str, tolerance: int = 300) -> None:
    """Raise ValueError if Stripe-Signature does not match the raw body."""
    if not secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET is not set")
    parts: dict[str, list[str]] = {}
    for item in (header or "").split(","):
        key, _, value = item.strip().partition("=")
        if key and value:
            parts.setdefault(key, []).append(value)
    timestamp = (parts.get("t") or [""])[0]
    signatures = parts.get("v1") or []
    if not timestamp or not signatures:
        raise ValueError("Invalid Stripe-Signature header")
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise ValueError("Invalid Stripe-Signature timestamp") from exc
    if abs(time.time() - ts) > tolerance:
        raise ValueError("Stripe-Signature timestamp is too old")
    signed = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise ValueError("Invalid Stripe-Signature")


def parse_webhook_event(payload: bytes, header: str) -> dict:
    verify_webhook_signature(payload, header, stripe_webhook_secret())
    try:
        event = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid webhook JSON") from exc
    if not isinstance(event, dict):
        raise ValueError("Invalid webhook payload")
    return event


def refund_payment(session: dict) -> None:
    """Refund a paid Checkout session. Best-effort; logs and continues on failure."""
    intent = session.get("payment_intent")
    if isinstance(intent, dict):
        intent = intent.get("id")
    intent_id = str(intent or "").strip()
    if not intent_id.startswith("pi_"):
        logger.warning("Cannot refund session %s: no payment_intent", session.get("id"))
        return
    try:
        _stripe_request("POST", "/refunds", {"payment_intent": intent_id})
        logger.warning("Refunded Stripe payment %s for session %s", intent_id, session.get("id"))
    except Exception:
        logger.exception("Stripe refund failed for %s", intent_id)
        raise
