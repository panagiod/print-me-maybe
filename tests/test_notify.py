"""Order notification emails for the studio inbox."""

from __future__ import annotations

import json
from email.message import EmailMessage
from io import BytesIO
import urllib.error

import pytest
from fastapi.testclient import TestClient

from src.db import init_schema
from src.main import app
from src.models import Order, OrderItem, format_money
from src.notify import build_order_email, mail_configured, notify_new_order
from src.seed import seed_products


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _sample_order() -> Order:
    return Order(
        id=12,
        customer_name="Ada Lovelace",
        customer_email="ada@example.com",
        shipping_address="12 Engine St\nNicosia",
        total_cents=750,
        created_at="2026-08-26",
        items=[
            OrderItem(product_name="Floral Glasses Case", quantity=1, unit_price_cents=400),
        ],
        status="new",
        lookup_token="customer-order-token-12",
    )


def test_mail_skipped_without_transport(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert mail_configured() is False
    assert notify_new_order(_sample_order()) is False


def test_notify_sends_via_resend(monkeypatch) -> None:
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.setenv("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    captured: list[tuple[str, dict]] = []

    class FakeResp:
        status = 200

        def read(self) -> bytes:
            return b'{"id":"email_1"}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=None):
        captured.append((req.full_url, json.loads(req.data.decode())))
        assert req.get_header("Authorization") == "Bearer re_test_key"
        return FakeResp()

    monkeypatch.setattr("src.notify.urllib.request.urlopen", fake_urlopen)
    assert mail_configured() is True
    assert notify_new_order(_sample_order()) is True
    assert len(captured) == 2
    studio = captured[0][1]
    customer = captured[1][1]
    assert studio["to"] == ["dimitrioupanagiotis@outlook.com"]
    assert "Floral Glasses Case" in studio["text"]
    assert studio["reply_to"] == "ada@example.com"
    assert customer["to"] == ["ada@example.com"]
    assert "View your order:" in customer["text"]
    assert "customer-order-token-12" in customer["text"]


def test_build_order_email_includes_customer_and_totals() -> None:
    msg = build_order_email(_sample_order())
    body = msg.get_content()
    assert msg["To"] == "dimitrioupanagiotis@outlook.com"
    assert msg["Reply-To"] == "ada@example.com"
    assert "order #12" in msg["Subject"]
    assert format_money(750) in msg["Subject"]
    assert "Ada Lovelace" in body
    assert "ada@example.com" in body
    assert "Floral Glasses Case × 1" in body
    assert "€4.00" in body
    assert "€3.50" in body
    assert "€7.50" in body
    assert "/admin/orders/12" in body
    assert "No payment was collected" in body


def test_notify_sends_via_smtp(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com")
    monkeypatch.setenv("SMTP_USER", "dimitrioupanagiotis@outlook.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_HOST", "smtp-mail.outlook.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    assert mail_configured() is True

    sent: list[EmailMessage] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, context=None):
            return None

        def login(self, user, password):
            assert user == "dimitrioupanagiotis@outlook.com"
            assert password == "app-password"

        def send_message(self, msg):
            sent.append(msg)

    monkeypatch.setattr("src.notify.smtplib.SMTP", FakeSMTP)
    assert notify_new_order(_sample_order()) is True
    assert len(sent) == 2
    assert sent[0]["To"] == "dimitrioupanagiotis@outlook.com"
    assert "Floral Glasses Case" in sent[0].get_content()
    assert sent[1]["To"] == "ada@example.com"
    assert "/order/customer-order-token-12" in sent[1].get_content()
    assert "/admin/" not in sent[1].get_content()


def test_notify_failure_does_not_raise(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_PASSWORD", "bad")
    monkeypatch.setenv("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com")

    class BoomSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError("smtp down")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("src.notify.smtplib.SMTP", BoomSMTP)
    assert notify_new_order(_sample_order()) is False


def test_checkout_emails_studio(monkeypatch) -> None:
    init_schema()
    seed_products()
    mailed: list[int] = []

    def fake_notify(order):
        mailed.append(order.id)
        assert order.customer_email == "ada@example.com"
        return True

    monkeypatch.setattr("src.main.schedule_order_email", fake_notify)

    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Ada Lovelace",
            "customer_email": "ada@example.com",
            "shipping_method": "delivery",
            "delivery_country": "cyprus",
            "shipping_address": "12 Engine St",
        },
    )
    assert checkout.status_code == 200
    assert "Thank you" in checkout.text
    assert len(mailed) == 1


def test_attack_alert_cooldown(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("ATTACK_ALERT_COOLDOWN", "3600")
    delivered: list[str] = []

    def fake_deliver(**kwargs):
        delivered.append(kwargs["subject"])

    monkeypatch.setattr("src.notify._deliver_studio", fake_deliver)
    from src.notify import notify_attack

    assert notify_attack("login", "203.0.113.9") is True
    assert notify_attack("login", "203.0.113.9") is False
    assert notify_attack("checkout", "203.0.113.9") is True
    assert notify_attack("ip", "203.0.113.9") is False
    assert len(delivered) == 2
    assert "login" in delivered[0].lower()
    assert "checkout" in delivered[1].lower()


def test_first_attack_alert_works_when_clock_is_under_cooldown(monkeypatch) -> None:
    """Fresh hosts (CI, Render cold start) have a small monotonic clock."""
    monkeypatch.setenv("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("ATTACK_ALERT_COOLDOWN", "3600")
    monkeypatch.setattr("src.notify.time.monotonic", lambda: 12.0)
    delivered: list[str] = []
    monkeypatch.setattr("src.notify._deliver_studio", lambda **kw: delivered.append(kw["subject"]))
    from src.notify import notify_attack

    assert notify_attack("login", "203.0.113.9") is True
    assert notify_attack("login", "203.0.113.9") is False
    assert delivered


def test_health_reports_mail_flag(monkeypatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    from fastapi.testclient import TestClient

    from src.main import app

    client = TestClient(app)
    assert client.get("/health").json()["mail"] is False
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com")
    assert client.get("/health").json()["mail"] is True


def test_send_test_email_explains_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    from src.notify import send_test_email

    ok, message = send_test_email()
    assert ok is False
    assert "RESEND_API_KEY" in message
    assert "resend.com" in message
    assert "/etc/eshop.env" in message


def test_send_test_email_explains_own_inbox_rule(monkeypatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com")

    class FakeError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                url="https://api.resend.com/emails",
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=BytesIO(
                    b'{"statusCode":403,"name":"validation_error",'
                    b'"message":"You can only send testing emails to your own email address (me@example.com)."}'
                ),
            )

    def boom(*args, **kwargs):
        raise FakeError()

    monkeypatch.setattr("src.notify.urllib.request.urlopen", boom)
    from src.notify import send_test_email

    ok, message = send_test_email()
    assert ok is False
    assert "signed up with" in message.lower() or "NOTIFY_EMAIL" in message


def test_send_test_email_explains_unverified_from_domain(monkeypatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("NOTIFY_EMAIL", "dimitrioupanagiotis@outlook.com")

    class FakeError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                url="https://api.resend.com/emails",
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=BytesIO(
                    b'{"statusCode":403,"name":"validation_error",'
                    b'"message":"The example.com domain is not verified. '
                    b'Please, add and verify your domain on https://resend.com/domains"}'
                ),
            )

    def boom(*args, **kwargs):
        raise FakeError()

    monkeypatch.setattr("src.notify.urllib.request.urlopen", boom)
    from src.notify import send_test_email

    ok, message = send_test_email()
    assert ok is False
    assert "resend.com/domains" in message
    assert "RESEND_FROM" in message
    assert "outlook.com" in message.lower()


def test_studio_orders_warns_when_from_is_resend_dev(monkeypatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.delenv("RESEND_FROM", raising=False)
    init_schema()
    seed_products()
    client = TestClient(app)
    client.post("/admin/login", data={"password": "printmemaybe"})
    page = client.get("/admin/orders")
    assert page.status_code == 200
    assert "resend.com/domains" in page.text
    assert "RESEND_FROM" in page.text
    assert "Mail is on for this server" not in page.text
