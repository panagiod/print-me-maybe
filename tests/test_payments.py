"""Stripe Checkout redirect and paid-session handling."""

from __future__ import annotations

import json
from io import BytesIO
import urllib.error

from fastapi.testclient import TestClient

from src.db import init_schema
from src.main import app
from src.seed import seed_products


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    init_schema()
    seed_products()
    return TestClient(app)


def test_checkout_without_stripe_still_places_order(tmp_path, monkeypatch) -> None:
    client = _client(monkeypatch, tmp_path)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    page = client.get("/checkout")
    assert "Place order" in page.text
    assert "/static/js/checkout.js" in page.text
    result = client.post(
        "/checkout",
        data={
            "customer_name": "Ada Lovelace",
            "customer_email": "ada@example.com",
            "shipping_method": "delivery",
            "delivery_country": "cyprus",
            "shipping_address": "12 Engine St",
        },
    )
    assert result.status_code == 200
    assert "Thank you" in result.text
    assert "No payment was collected" in result.text


def test_checkout_with_stripe_redirects(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("SHOP_URL", "https://printmemaybe.example")

    def fake_urlopen(req, timeout=20):
        assert b"line_items" in (req.data or b"")
        payload = json.dumps({"id": "cs_test_123", "url": "https://checkout.stripe.com/c/pay/cs_test_123"}).encode()

        class Resp:
            def read(self):
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return Resp()

    monkeypatch.setattr("src.payments.urllib.request.urlopen", fake_urlopen)
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    page = client.get("/checkout")
    assert "Pay with card" in page.text
    result = client.post(
        "/checkout",
        data={
            "customer_name": "Ada Lovelace",
            "customer_email": "ada@example.com",
            "shipping_method": "delivery",
            "delivery_country": "cyprus",
            "shipping_address": "12 Engine St",
        },
        follow_redirects=False,
    )
    assert result.status_code == 303
    assert "checkout.stripe.com" in result.headers["location"]


def test_pay_success_rejects_unpaid_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")

    class FakeError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                url="https://api.stripe.com/v1/checkout/sessions/cs_bad",
                code=404,
                msg="Not Found",
                hdrs=None,
                fp=BytesIO(b'{"error":{"message":"No such session"}}'),
            )

    def boom(*args, **kwargs):
        raise FakeError()

    monkeypatch.setattr("src.payments.urllib.request.urlopen", boom)
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    result = client.get("/pay/success?session_id=cs_bad")
    assert result.status_code == 400


def test_pay_success_creates_paid_order_from_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    payload = {
        "id": "cs_test_paid",
        "payment_status": "paid",
        "amount_total": 400,
        "currency": "eur",
        "metadata": {
            "customer_name": "Ada Lovelace",
            "customer_email": "ada@example.com",
            "shipping_address": "12 Engine St",
            "shipping_method": "pickup",
            "delivery_country": "",
            "shipping_cents": "0",
            "total_cents": "400",
            "cart": json.dumps([[glasses["id"], 1]], separators=(",", ":")),
        },
    }

    def fake_urlopen(req, timeout=20):
        class Resp:
            def read(self):
                return json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return Resp()

    monkeypatch.setattr("src.payments.urllib.request.urlopen", fake_urlopen)
    result = client.get("/pay/success?session_id=cs_test_paid")
    assert result.status_code == 200
    assert "Payment received" in result.text
    assert "#1" in result.text

    login = client.post("/admin/login", data={"password": "printmemaybe"}, follow_redirects=False)
    assert login.status_code == 303
    orders = client.get("/admin/orders")
    assert "Paid" in orders.text
    assert "Ada Lovelace" in orders.text

    again = client.get("/pay/success?session_id=cs_test_paid")
    assert again.status_code == 200
    assert "#1" in again.text


def _stripe_signature(payload: bytes, secret: str) -> str:
    import hashlib
    import hmac
    import time

    ts = str(int(time.time()))
    digest = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def test_stripe_webhook_creates_order_without_success_page(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    from src.store import get_order, get_product, list_orders, save_pending_checkout
    from src.models import CartLine

    product = get_product(glasses["id"])
    assert product
    save_pending_checkout(
        session_id="cs_test_webhook",
        lines=[CartLine(product=product, quantity=1)],
        customer_name="Webhook User",
        customer_email="web@example.com",
        shipping_address="Pick up at studio",
        shipping_method="pickup",
        delivery_country="",
        shipping_cents=0,
        total_cents=400,
    )
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_webhook",
                "payment_status": "paid",
                "amount_total": 400,
                "payment_intent": "pi_test_ok",
                "metadata": {},
            }
        },
    }
    payload = json.dumps(event).encode()
    result = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": _stripe_signature(payload, "whsec_test")},
    )
    assert result.status_code == 200
    order = get_order(1)
    assert order is not None
    assert order.paid
    assert order.customer_name == "Webhook User"
    assert order.shipping_method == "pickup"

    again = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": _stripe_signature(payload, "whsec_test")},
    )
    assert again.status_code == 200
    assert len(list_orders()) == 1


def test_stripe_webhook_rejects_bad_signature(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    payload = b'{"type":"checkout.session.completed","data":{"object":{}}}'
    result = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": "t=1,v1=deadbeef"},
    )
    assert result.status_code == 400


def test_paid_session_refunds_when_stock_is_gone(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("NOTIFY_EMAIL", "studio@example.com")
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    from src.store import get_product, save_pending_checkout, set_product_stock, list_orders
    from src.models import CartLine

    product = get_product(glasses["id"])
    assert product
    save_pending_checkout(
        session_id="cs_test_nostock",
        lines=[CartLine(product=product, quantity=1)],
        customer_name="Late Buyer",
        customer_email="late@example.com",
        shipping_address="Pick up at studio",
        shipping_method="pickup",
        delivery_country="",
        shipping_cents=0,
        total_cents=400,
    )
    set_product_stock(product.id, 0)
    refunds: list[str] = []
    mail: list[dict] = []

    def fake_urlopen(req, timeout=20):
        url = req.full_url
        if url.endswith("/refunds"):
            refunds.append(req.data.decode() if req.data else "")

            class Resp:
                def read(self):
                    return b'{"id":"re_test"}'

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return Resp()
        mail.append(json.loads(req.data.decode()))

        class MailResp:
            status = 200

            def read(self):
                return b'{"id":"email_1"}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return MailResp()

    monkeypatch.setattr("src.payments.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("src.notify.urllib.request.urlopen", fake_urlopen)
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_nostock",
                "payment_status": "paid",
                "amount_total": 400,
                "payment_intent": "pi_test_refund",
                "metadata": {},
            }
        },
    }
    payload = json.dumps(event).encode()
    result = client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": _stripe_signature(payload, "whsec_test")},
    )
    assert result.status_code == 200
    assert list_orders() == []
    assert any("pi_test_refund" in body for body in refunds)
    assert any("paid checkout failed" in (m.get("subject") or "").lower() for m in mail)

