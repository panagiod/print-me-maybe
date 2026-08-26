"""Stripe Checkout (hosted). No monthly Stripe fee — only a % on paid cards."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

STRIPE_API = "https://api.stripe.com/v1"
DEFAULT_SHOP_URL = "http://127.0.0.1:8000"


def stripe_secret_key() -> str:
    return os.environ.get("STRIPE_SECRET_KEY", "").strip()


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
) -> str:
    """Return the hosted Stripe Checkout URL. Amounts are in EUR cents."""
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
    # Stripe line items are products only; add shipping as its own line when charged.
    shipping = total_cents - sum(line.line_total_cents for line in lines)
    if shipping > 0:
        i = len(lines)
        payload[f"line_items[{i}][quantity]"] = "1"
        payload[f"line_items[{i}][price_data][currency]"] = "eur"
        payload[f"line_items[{i}][price_data][unit_amount]"] = str(shipping)
        payload[f"line_items[{i}][price_data][product_data][name]"] = "Shipping"
    session = _stripe_request("POST", "/checkout/sessions", payload)
    url = session.get("url")
    if not url:
        raise RuntimeError("Stripe did not return a checkout URL")
    return str(url)


def paid_session(session_id: str) -> dict | None:
    """Return the Stripe session if it is paid; otherwise None."""
    cleaned = (session_id or "").strip()
    if not cleaned.startswith("cs_"):
        return None
    session = _stripe_request("GET", f"/checkout/sessions/{urllib.parse.quote(cleaned)}")
    if session.get("payment_status") != "paid":
        return None
    return session
