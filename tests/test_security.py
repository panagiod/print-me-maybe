"""Security headers, secrets, cart stock caps, and private order URLs."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from src.db import init_schema
from src.main import app
from src.security import require_production_secrets
from src.seed import seed_products
from src.store import get_product, list_all_products, set_product_stock


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RATE_LIMIT_DISABLED", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("ENV", raising=False)


def test_security_headers_on_home() -> None:
    init_schema()
    seed_products()
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "strict-origin-when-cross-origin" in response.headers["referrer-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    csp = response.headers["content-security-policy"]
    assert "form-action 'self' https://checkout.stripe.com" in csp
    assert "strict-transport-security" not in response.headers


def test_hsts_when_forwarded_https() -> None:
    init_schema()
    seed_products()
    client = TestClient(app)
    response = client.get("/", headers={"x-forwarded-proto": "https"})
    assert "max-age=31536000" in response.headers.get("strict-transport-security", "")


def test_production_requires_secrets(monkeypatch) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        require_production_secrets()
    monkeypatch.setenv("SESSION_SECRET", "not-a-dev-default-secret")
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        require_production_secrets()
    monkeypatch.setenv("ADMIN_PASSWORD", "studio-only")
    require_production_secrets()


def test_cart_add_caps_at_stock() -> None:
    init_schema()
    seed_products()
    glasses = next(p for p in list_all_products() if p.slug == "glasses-case")
    set_product_stock(glasses.id, 2)
    client = TestClient(app)
    client.post("/cart/add", data={"product_id": glasses.id, "quantity": 9})
    cart = client.get("/cart")
    assert cart.status_code == 200
    assert 'value="2"' in cart.text
    client.post("/cart/update", data={"product_id": glasses.id, "quantity": 50})
    cart = client.get("/cart")
    assert 'value="2"' in cart.text
    assert get_product(glasses.id).stock == 2


def test_failed_login_is_logged(caplog) -> None:
    init_schema()
    seed_products()
    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="src.admin"):
        denied = client.post("/admin/login", data={"password": "wrong"})
    assert denied.status_code == 401
    assert any("Failed admin login" in rec.message for rec in caplog.records)
    assert "wrong" not in caplog.text
