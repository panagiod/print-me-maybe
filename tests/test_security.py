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
        denied = client.post("/studio/login", data={"password": "wrong"})
    assert denied.status_code == 401
    assert any("Failed admin login" in rec.message for rec in caplog.records)
    assert "wrong" not in caplog.text


def test_listing_photo_accepts_head() -> None:
    init_schema()
    seed_products()
    client = TestClient(app)
    glasses = next(p for p in list_all_products() if p.slug == "glasses-case")
    photo = client.get(glasses.image_url)
    assert photo.status_code == 200
    head = client.head(glasses.image_url)
    assert head.status_code == 200
    assert head.headers["content-type"].startswith("image/")


def test_studio_csrf_rejects_login_without_token(monkeypatch) -> None:
    monkeypatch.delenv("CSRF_DISABLED", raising=False)
    init_schema()
    seed_products()
    client = TestClient(app)
    missing = client.post("/studio/login", data={"password": "printmemaybe"}, follow_redirects=False)
    assert missing.status_code == 403
    login_page = client.get("/studio/login")
    token = login_page.text.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    assert len(token) >= 16
    ok = client.post(
        "/studio/login",
        data={"password": "printmemaybe", "csrf_token": token},
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert ok.headers["location"] == "/studio/orders"


def test_studio_session_expires_without_clearing_cart(monkeypatch) -> None:
    init_schema()
    seed_products()
    client = TestClient(app)
    glasses = next(p for p in list_all_products() if p.slug == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses.id, "quantity": 1})
    client.post("/studio/login", data={"password": "printmemaybe"})
    assert client.get("/studio/orders").status_code == 200
    monkeypatch.setattr("src.security.admin_session_seconds", lambda: 0)
    expired = client.get("/studio/orders", follow_redirects=False)
    assert expired.status_code == 303
    assert expired.headers["location"] == "/studio/login"
    cart = client.get("/cart")
    assert "Floral Glasses Case" in cart.text


def test_studio_path_default_and_override(monkeypatch) -> None:
    from src.security import studio_path, studio_url

    monkeypatch.delenv("ADMIN_PATH", raising=False)
    assert studio_path() == "/studio"
    assert studio_url("/login") == "/studio/login"
    monkeypatch.setenv("ADMIN_PATH", "backoffice")
    assert studio_path() == "/backoffice"
    monkeypatch.setenv("ADMIN_PATH", "/cart")
    assert studio_path() == "/studio"
