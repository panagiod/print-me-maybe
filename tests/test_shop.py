"""Smoke tests for the Print Me Maybe shop."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.db import get_connection, init_schema
from src.main import app
from src.models import CYPRUS_SHIPPING_CENTS, INTERNATIONAL_SHIPPING_CENTS, order_total_cents, shipping_cents
from src.seed import seed_products
from src.store import get_order, list_all_products


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def test_health_and_catalog() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["mail"] is False
    assert payload.get("payments") is False
    assert payload.get("persistent") is False

    home = client.get("/")
    assert home.status_code == 200
    assert "Print Me Maybe" in home.text
    assert "LaserCraft 27" in home.text
    assert "print.me.maybe" in home.text
    assert "lasercraft.27" in home.text
    assert "Made in Cyprus" in home.text
    assert 'name="viewport"' in home.text
    assert "viewport-fit=cover" in home.text
    assert "Floral Glasses Case" in home.text
    assert "€4.00" in home.text
    assert "Custom Cake Topper" in home.text
    assert "€15.00" in home.text
    assert "Teddy Bear Keychain" in home.text
    assert "€5.00" in home.text
    assert "/static/images/products/glasses-case.jpg" in home.text

    api = client.get("/api/products")
    assert api.status_code == 200
    products = api.json()
    assert len(products) >= 1
    categories = {p["category"] for p in products}
    assert "3D Prints" in categories
    assert "Laser Engraving" in categories


def test_category_filter() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    prints = client.get("/?category=3D Prints")
    assert prints.status_code == 200
    assert "Floral Glasses Case" in prints.text
    assert "Engraved Oak Coaster Set" not in prints.text

    laser = client.get("/?category=Laser Engraving")
    assert laser.status_code == 200
    assert "Engraved Oak Coaster Set" in laser.text
    assert "Floral Glasses Case" not in laser.text


def test_shipping_calculation() -> None:
    assert shipping_cents("pickup") == 0
    assert shipping_cents("delivery", "cyprus") == CYPRUS_SHIPPING_CENTS
    assert shipping_cents("delivery", "other") == INTERNATIONAL_SHIPPING_CENTS
    assert order_total_cents(400, "delivery", "cyprus") == 400 + CYPRUS_SHIPPING_CENTS
    assert order_total_cents(400, "delivery", "other") == 400 + INTERNATIONAL_SHIPPING_CENTS


def test_add_to_cart_and_checkout_with_shipping() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    subtotal = glasses["price_cents"]
    shipping = shipping_cents("delivery", "other")
    total = order_total_cents(subtotal, "delivery", "other")

    add = client.post(
        "/cart/add",
        data={"product_id": glasses["id"], "quantity": 1},
        follow_redirects=False,
    )
    assert add.status_code == 303

    cart = client.get("/cart")
    assert cart.status_code == 200
    assert glasses["name"] in cart.text
    assert "Calculated at checkout" in cart.text
    assert 'data-label="Product"' in cart.text
    assert 'data-label="Qty"' in cart.text
    assert "table-wrap" in cart.text

    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Test User",
            "customer_email": "test@example.com",
            "shipping_method": "delivery",
            "delivery_country": "other",
            "shipping_address": "123 Test St, London",
            "customer_phone": "+357 99 123456",
            "customer_notes": "navy, name Eleni",
        },
    )
    assert checkout.status_code == 200
    assert "Thank you" in checkout.text
    assert f"€{total / 100:.2f}" in checkout.text

    order_id = checkout.text.split("#")[1].split("<")[0]
    token = checkout.text.split('href="/order/')[1].split('"')[0]
    assert token != order_id
    assert client.get(f"/order/{order_id}").status_code == 404
    detail = client.get(f"/order/{token}")
    assert detail.status_code == 200
    assert glasses["name"] in detail.text
    assert f"€{shipping / 100:.2f}" in detail.text or "Free" in detail.text
    assert "navy, name Eleni" in detail.text
    from src.store import get_order

    order = get_order(int(order_id))
    assert order is not None
    assert order.customer_notes == "navy, name Eleni"
    assert order.customer_phone == "+357 99 123456"


def test_pickup_checkout_is_free() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    subtotal = glasses["price_cents"]

    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})

    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Pick Up Pat",
            "customer_email": "pickup@example.com",
            "shipping_method": "pickup",
        },
    )
    assert checkout.status_code == 200
    assert f"€{subtotal / 100:.2f}" in checkout.text


def test_cyprus_delivery_charges_standard_shipping() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    total = glasses["price_cents"] + CYPRUS_SHIPPING_CENTS

    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Cyprus Customer",
            "customer_email": "cyprus@example.com",
            "shipping_method": "delivery",
            "delivery_country": "cyprus",
            "shipping_address": "12 Engine St, Nicosia",
            "customer_phone": "+357 99 123456",
        },
    )
    assert checkout.status_code == 200
    assert f"€{total / 100:.2f}" in checkout.text
    assert "€3.50" in checkout.text
    order_id = int(checkout.text.split("#")[1].split("<")[0])
    from src.store import get_order

    order = get_order(order_id)
    assert order is not None
    assert order.shipping_method == "delivery"
    assert order.delivery_country == "cyprus"
    assert order.shipping_label == "Delivery in Cyprus"


def test_admin_requires_login() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    listing = client.get("/admin/orders", follow_redirects=False)
    assert listing.status_code == 303
    assert listing.headers["location"] == "/admin/login"


def test_admin_orders_and_stock() -> None:
    init_schema()
    seed_products()

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
            "customer_phone": "+357 99 123456",
        },
    )
    assert "Thank you" in checkout.text
    order_id = checkout.text.split("#")[1].split("<")[0]

    denied = client.post("/admin/login", data={"password": "wrong"}, follow_redirects=False)
    assert denied.status_code == 401

    login = client.post("/admin/login", data={"password": "printmemaybe"}, follow_redirects=False)
    assert login.status_code == 303

    orders = client.get("/admin/orders")
    assert orders.status_code == 200
    assert "Ada Lovelace" in orders.text
    assert f">{order_id}<" in orders.text or f"/admin/orders/{order_id}" in orders.text
    assert 'data-label="Customer"' in orders.text
    assert 'data-label="Ship"' in orders.text
    assert "table-wrap" in orders.text
    assert "Send test email" in orders.text
    assert "Search orders" in orders.text
    assert "Pickup" in orders.text
    assert "/etc/eshop.env" in orders.text
    assert "resend.com" in orders.text
    assert "RESEND_API_KEY" in orders.text

    save = client.post(
        f"/admin/orders/{order_id}",
        data={"status": "in_progress", "notes": "DM received for custom name"},
        follow_redirects=False,
    )
    assert save.status_code == 303

    detail = client.get(f"/admin/orders/{order_id}")
    assert detail.status_code == 200
    assert "In progress" in detail.text
    assert "DM received for custom name" in detail.text
    assert "Tracking number" in detail.text
    assert "Copy customer link" in detail.text
    assert "Print packing slip" in detail.text
    assert "Mark as paid (cash/bank)" in detail.text
    assert "refunds through Stripe" in detail.text
    assert "+357 99 123456" in detail.text

    stock_page = client.get("/admin/stock")
    assert stock_page.status_code == 200
    assert glasses["name"] in stock_page.text
    assert "Add a product" in stock_page.text
    assert 'data-label="Qty"' in stock_page.text

    client.post(f"/admin/stock/{glasses['id']}", data={"stock": "0"})
    hidden = client.get("/api/products").json()
    assert all(p["id"] != glasses["id"] for p in hidden)


def test_cancel_restocks_and_reopen_deducts() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    before = next(p for p in list_all_products() if p.slug == "glasses-case").stock

    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Cancel Case",
            "customer_email": "cancel@example.com",
            "shipping_method": "pickup",
        },
    )
    order_id = checkout.text.split("#")[1].split("<")[0]
    after_order = next(p for p in list_all_products() if p.slug == "glasses-case").stock
    assert after_order == before - 1

    client.post("/admin/login", data={"password": "printmemaybe"})
    client.post(
        f"/admin/orders/{order_id}",
        data={"status": "cancelled", "notes": ""},
    )
    after_cancel = next(p for p in list_all_products() if p.slug == "glasses-case").stock
    assert after_cancel == before
    cancelled = client.get(f"/admin/orders/{order_id}")
    assert "Cancelled" in cancelled.text
    assert "Unpaid" in cancelled.text
    assert 'status-refunded' not in cancelled.text

    client.post(
        f"/admin/orders/{order_id}",
        data={"status": "in_progress", "notes": ""},
    )
    after_reopen = next(p for p in list_all_products() if p.slug == "glasses-case").stock
    assert after_reopen == before - 1


def test_shipped_tracking_number_shows_on_customer_page() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Ship Me",
            "customer_email": "ship@example.com",
            "shipping_method": "delivery",
            "delivery_country": "cyprus",
            "shipping_address": "12 Engine St",
            "customer_phone": "+357 99 123456",
        },
    )
    order_id = checkout.text.split("#")[1].split("<")[0]
    token = checkout.text.split('href="/order/')[1].split('"')[0]

    client.post("/admin/login", data={"password": "printmemaybe"})
    save = client.post(
        f"/admin/orders/{order_id}",
        data={
            "status": "shipped",
            "notes": "",
            "tracking_number": "CY123456789CY",
        },
        follow_redirects=False,
    )
    assert save.status_code == 303
    order = get_order(int(order_id))
    assert order is not None
    assert order.status == "shipped"
    assert order.tracking_number == "CY123456789CY"

    admin_page = client.get(f"/admin/orders/{order_id}")
    assert "CY123456789CY" in admin_page.text
    assert "Shipped" in admin_page.text

    detail = client.get(f"/order/{token}")
    assert detail.status_code == 200
    assert "Shipped" in detail.text
    assert "CY123456789CY" in detail.text
    assert "Tracking:" in detail.text


def test_seed_keeps_admin_price_and_stock() -> None:
    init_schema()
    seed_products()
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET price_cents = 1, stock = 7 WHERE slug = 'custom-cake-topper'"
        )
    seed_products()
    product = next(p for p in list_all_products() if p.slug == "custom-cake-topper")
    assert product.price_cents == 1
    assert product.stock == 7


_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_admin_add_product_shows_in_shop() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    guest = client.post(
        "/admin/products",
        data={
            "name": "Studio Test Vase",
            "description": "A custom 3D vase.",
            "price": "12.50",
            "category": "3D Prints",
            "stock": "4",
        },
        follow_redirects=False,
    )
    assert guest.status_code == 303
    assert guest.headers["location"] == "/admin/login"

    client.post("/admin/login", data={"password": "printmemaybe"})
    created = client.post(
        "/admin/products",
        data={
            "name": "Studio Test Vase",
            "description": "A custom 3D vase.",
            "price": "12.50",
            "category": "3D Prints",
            "stock": "4",
        },
        files={"image": ("vase.png", _PNG_1X1, "image/png")},
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"] == "/admin/stock"

    product = next(p for p in list_all_products() if p.slug == "studio-test-vase")
    assert product.price_cents == 1250
    assert product.stock == 4
    assert product.image_url.startswith("/media/products/")

    home = client.get("/")
    assert "Studio Test Vase" in home.text
    assert "€12.50" in home.text

    photo = client.get(product.image_url)
    assert photo.status_code == 200
    assert photo.content[:8] == b"\x89PNG\r\n\x1a\n"

    seed_products()
    still_there = next(p for p in list_all_products() if p.slug == "studio-test-vase")
    assert still_there.price_cents == 1250


def test_admin_edit_product() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    client.post("/admin/login", data={"password": "printmemaybe"})
    product = next(p for p in list_all_products() if p.slug == "glasses-case")
    page = client.get(f"/admin/products/{product.id}/edit")
    assert page.status_code == 200
    assert product.name in page.text

    saved = client.post(
        f"/admin/products/{product.id}/edit",
        data={
            "name": "Floral Case Updated",
            "description": "Updated description.",
            "price": "6.50",
            "category": "3D Prints",
            "stock": "9",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    updated = next(p for p in list_all_products() if p.id == product.id)
    assert updated.name == "Floral Case Updated"
    assert updated.price_cents == 650
    assert updated.stock == 9
    assert updated.slug == "glasses-case"
    home = client.get("/")
    assert "Floral Case Updated" in home.text
    assert "€6.50" in home.text


def test_admin_delete_product() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    client.post("/admin/login", data={"password": "printmemaybe"})
    created = client.post(
        "/admin/products",
        data={
            "name": "Delete Me Mug",
            "description": "Temporary product.",
            "price": "8.00",
            "category": "3D Prints",
            "stock": "2",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303

    product = next(p for p in list_all_products() if p.slug == "delete-me-mug")
    deleted = client.post(
        f"/admin/products/{product.id}/delete",
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert all(p.slug != "delete-me-mug" for p in list_all_products())


def test_admin_cannot_delete_ordered_product() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    client.post(
        "/checkout",
        data={
            "customer_name": "Buyer",
            "customer_email": "buyer@example.com",
            "shipping_method": "pickup",
        },
    )

    client.post("/admin/login", data={"password": "printmemaybe"})
    blocked = client.post(f"/admin/products/{glasses['id']}/delete")
    assert blocked.status_code == 400
    assert "ordered" in blocked.text.lower()
    assert any(p.id == glasses["id"] for p in list_all_products())


def test_admin_add_product_rejects_bad_price() -> None:
    init_schema()
    seed_products()

    client = TestClient(app)
    client.post("/admin/login", data={"password": "printmemaybe"})
    bad = client.post(
        "/admin/products",
        data={
            "name": "Broken Price",
            "description": "Should not save.",
            "price": "free",
            "category": "Laser Engraving",
            "stock": "1",
        },
    )
    assert bad.status_code == 400
    assert "price" in bad.text.lower()
    assert all(p.slug != "broken-price" for p in list_all_products())


def test_delivery_checkout_requires_phone() -> None:
    init_schema()
    seed_products()
    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    page = client.get("/checkout")
    assert 'name="customer_notes"' in page.text
    assert 'name="customer_phone"' in page.text
    blocked = client.post(
        "/checkout",
        data={
            "customer_name": "No Phone",
            "customer_email": "nophone@example.com",
            "shipping_method": "delivery",
            "delivery_country": "cyprus",
            "shipping_address": "12 Engine St",
        },
    )
    assert blocked.status_code == 400
    assert "phone" in blocked.text.lower()


def test_sold_out_product_hides_add_to_cart() -> None:
    init_schema()
    seed_products()
    glasses = next(p for p in list_all_products() if p.slug == "glasses-case")
    from src.store import set_product_stock

    set_product_stock(glasses.id, 0)
    client = TestClient(app)
    page = client.get(f"/product/{glasses.slug}")
    assert page.status_code == 200
    assert "Sold out" in page.text
    assert "Add to cart" not in page.text
    add = client.post(
        "/cart/add",
        data={"product_id": glasses.id, "quantity": 1},
        follow_redirects=False,
    )
    assert add.status_code == 303
    assert "sold_out=1" in add.headers["location"]
    shown = client.get(add.headers["location"])
    assert "cannot be added to the cart" in shown.text


def test_order_list_search_and_shipping_filter() -> None:
    init_schema()
    seed_products()
    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    client.post(
        "/checkout",
        data={
            "customer_name": "Eleni Search",
            "customer_email": "eleni@example.com",
            "shipping_method": "pickup",
        },
    )
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    client.post(
        "/checkout",
        data={
            "customer_name": "Nicos Courier",
            "customer_email": "nicos@example.com",
            "shipping_method": "delivery",
            "delivery_country": "cyprus",
            "shipping_address": "1 Ledra",
            "customer_phone": "+357 99 111111",
        },
    )
    client.post("/admin/login", data={"password": "printmemaybe"})
    search = client.get("/admin/orders?q=Eleni")
    assert "Eleni Search" in search.text
    assert "Nicos Courier" not in search.text
    pickup = client.get("/admin/orders?shipping=pickup")
    assert "Eleni Search" in pickup.text
    assert "Nicos Courier" not in pickup.text
    cyprus = client.get("/admin/orders?shipping=cyprus")
    assert "Nicos Courier" in cyprus.text
    assert "Eleni Search" not in cyprus.text


def test_cannot_reopen_refunded_order() -> None:
    init_schema()
    seed_products()
    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Refunded",
            "customer_email": "refunded@example.com",
            "shipping_method": "pickup",
        },
    )
    order_id = int(checkout.text.split("#")[1].split("<")[0])
    from src.store import set_payment_status, update_order_status

    update_order_status(order_id, "cancelled")
    set_payment_status(order_id, "refunded")
    client.post("/admin/login", data={"password": "printmemaybe"})
    reopen = client.post(
        f"/admin/orders/{order_id}",
        data={"status": "in_progress", "notes": ""},
    )
    assert reopen.status_code == 400
    assert "refunded" in reopen.text.lower()
    order = get_order(order_id)
    assert order is not None
    assert order.status == "cancelled"


def test_rename_does_not_change_past_order_names() -> None:
    init_schema()
    seed_products()
    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    original_name = glasses["name"]
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Name Snapshot",
            "customer_email": "snap@example.com",
            "shipping_method": "pickup",
        },
    )
    order_id = int(checkout.text.split("#")[1].split("<")[0])
    client.post("/admin/login", data={"password": "printmemaybe"})
    product = next(p for p in list_all_products() if p.id == glasses["id"])
    client.post(
        f"/admin/products/{product.id}/edit",
        data={
            "name": "Renamed Glasses",
            "description": product.description,
            "price": "4.00",
            "category": product.category,
            "stock": str(product.stock),
        },
    )
    order = get_order(order_id)
    assert order is not None
    assert order.items[0].product_name == original_name
    admin_page = client.get(f"/admin/orders/{order_id}")
    assert original_name in admin_page.text
    assert "Renamed Glasses" not in admin_page.text


def test_mark_paid_cash_and_cancel_skips_stripe(monkeypatch) -> None:
    init_schema()
    seed_products()
    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Cash Buyer",
            "customer_email": "cash@example.com",
            "shipping_method": "pickup",
        },
    )
    order_id = int(checkout.text.split("#")[1].split("<")[0])
    stripe_calls: list[str] = []

    def boom(*args, **kwargs):
        stripe_calls.append("called")
        raise AssertionError("Stripe should not be called for cash payments")

    monkeypatch.setattr("src.payments.urllib.request.urlopen", boom)
    client.post("/admin/login", data={"password": "printmemaybe"})
    marked = client.post(
        f"/admin/orders/{order_id}/mark-paid",
        follow_redirects=False,
    )
    assert marked.status_code == 303
    order = get_order(order_id)
    assert order is not None
    assert order.paid
    assert order.payment_method == "cash"
    cancelled = client.post(
        f"/admin/orders/{order_id}",
        data={"status": "cancelled", "notes": ""},
        follow_redirects=False,
    )
    assert cancelled.status_code == 303
    assert stripe_calls == []
    order = get_order(order_id)
    assert order is not None
    assert order.status == "cancelled"
    assert order.payment_status == "paid"


def test_ready_status_emails_customer_once(monkeypatch) -> None:
    init_schema()
    seed_products()
    mailed: list[int] = []

    def fake_ready(order):
        mailed.append(order.id)
        return True

    monkeypatch.setattr("src.admin.notify_order_ready", fake_ready)
    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Ready Pat",
            "customer_email": "ready@example.com",
            "shipping_method": "pickup",
        },
    )
    order_id = int(checkout.text.split("#")[1].split("<")[0])
    client.post("/admin/login", data={"password": "printmemaybe"})
    first = client.post(
        f"/admin/orders/{order_id}",
        data={"status": "ready", "notes": ""},
        follow_redirects=False,
    )
    assert first.status_code == 303
    assert "mail=sent" in first.headers["location"]
    second = client.post(
        f"/admin/orders/{order_id}",
        data={"status": "ready", "notes": ""},
        follow_redirects=False,
    )
    assert second.status_code == 303
    assert "mail=" not in second.headers["location"]
    assert mailed == [order_id]


def test_delivery_shipped_without_tracking_needs_number() -> None:
    init_schema()
    seed_products()
    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Need Track",
            "customer_email": "track@example.com",
            "shipping_method": "delivery",
            "delivery_country": "cyprus",
            "shipping_address": "12 Engine St",
            "customer_phone": "+357 99 123456",
        },
    )
    order_id = int(checkout.text.split("#")[1].split("<")[0])
    client.post("/admin/login", data={"password": "printmemaybe"})
    save = client.post(
        f"/admin/orders/{order_id}",
        data={"status": "shipped", "notes": "", "tracking_number": ""},
        follow_redirects=False,
    )
    assert save.status_code == 303
    assert "mail=need_tracking" in save.headers["location"]
    page = client.get(save.headers["location"])
    assert "Add a tracking number" in page.text


def test_packing_slip_and_nicosia_time() -> None:
    from src.models import format_local_time

    assert format_local_time("2026-08-26 10:00:00") == "2026-08-26 13:00"
    init_schema()
    seed_products()
    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Print Me",
            "customer_email": "print@example.com",
            "shipping_method": "pickup",
        },
    )
    order_id = int(checkout.text.split("#")[1].split("<")[0])
    client.post("/admin/login", data={"password": "printmemaybe"})
    slip = client.get(f"/admin/orders/{order_id}/print")
    assert slip.status_code == 200
    assert "Packing slip" in slip.text
    assert "Print Me" in slip.text
    from src.store import set_product_stock

    set_product_stock(glasses["id"], 0)
    stock = client.get("/admin/stock")
    assert "stock-zero" in stock.text
    assert 'data-confirm="Remove' in stock.text
    assert "/static/js/admin.js" in stock.text

