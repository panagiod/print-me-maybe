"""Rate limits on login, checkout, and request floods."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.db import init_schema
from src.main import app
from src.seed import seed_products


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RATE_LIMIT_DISABLED", raising=False)


def test_health_is_not_rate_limited(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_IP", "2")
    init_schema()
    seed_products()
    client = TestClient(app)
    for _ in range(8):
        response = client.get("/health")
        assert response.status_code == 200


def test_admin_login_blocks_after_too_many_tries(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_LOGIN", "3")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_WINDOW", "900")
    monkeypatch.setenv("ATTACK_ALERT_COOLDOWN", "3600")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    alerts: list[str] = []
    monkeypatch.setattr("src.notify._deliver_studio", lambda **kw: alerts.append(kw["subject"]))
    init_schema()
    seed_products()
    client = TestClient(app)
    for _ in range(3):
        denied = client.post("/studio/login", data={"password": "wrong"})
        assert denied.status_code == 401
    assert len(alerts) == 1
    assert "login" in alerts[0].lower()
    blocked = client.post("/studio/login", data={"password": "wrong"})
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after")
    assert "Too many attempts" in blocked.text
    still_blocked = client.post("/studio/login", data={"password": "printmemaybe"})
    assert still_blocked.status_code == 429
    assert len(alerts) == 1


def test_checkout_blocks_repeat_orders(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_CHECKOUT", "2")
    monkeypatch.setenv("RATE_LIMIT_CHECKOUT_WINDOW", "3600")
    monkeypatch.setenv("ATTACK_ALERT_COOLDOWN", "3600")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    alerts: list[str] = []
    monkeypatch.setattr("src.notify._deliver_studio", lambda **kw: alerts.append(kw["subject"]))
    init_schema()
    seed_products()
    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")

    def place() -> int:
        client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
        result = client.post(
            "/checkout",
            data={
                "customer_name": "Ada Lovelace",
                "customer_email": "ada@example.com",
                "shipping_method": "pickup",
            },
        )
        return result.status_code

    assert place() == 200
    assert place() == 200
    assert place() == 429
    assert any("blocked checkout" in subject.lower() for subject in alerts)


def test_page_flood_returns_429_without_security_email(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_IP", "5")
    alerts: list[str] = []
    monkeypatch.setattr("src.notify._deliver_studio", lambda **kw: alerts.append(kw["subject"]))
    init_schema()
    seed_products()
    client = TestClient(app)
    codes = [client.get("/").status_code for _ in range(6)]
    assert codes[:5] == [200, 200, 200, 200, 200]
    assert codes[5] == 429
    assert client.get("/").headers.get("retry-after")
    assert alerts == []
