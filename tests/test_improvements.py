"""Pillow thumbs, Alembic, HTMX stock cards, and packing-slip PDF."""

from __future__ import annotations

import sqlite3
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from src.db import db_path, init_schema, product_images_dir
from src.main import app
from src.seed import seed_products
from src.store import list_all_products
from src.uploads import DISPLAY_MAX, THUMB_MAX, image_thumb_url, process_image_bytes


def _jpeg_bytes(width: int, height: int, quality: int = 95) -> bytes:
    image = Image.new("RGB", (width, height), (40, 90, 140))
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def test_image_thumb_url_for_uploads_and_static() -> None:
    assert image_thumb_url("/media/products/vase-ab12.jpg") == "/media/products/vase-ab12-thumb.jpg"
    assert image_thumb_url("/media/products/vase-ab12-thumb.jpg") == "/media/products/vase-ab12-thumb.jpg"
    assert image_thumb_url("/static/images/products/glasses-case.jpg") == "/static/images/products/glasses-case.jpg"
    assert image_thumb_url("/static/images/products/laser-coasters.svg") == "/static/images/products/laser-coasters.svg"


def test_process_image_bytes_resizes_and_strips() -> None:
    original = _jpeg_bytes(2000, 1500)
    display, thumb = process_image_bytes(original)
    display_img = Image.open(BytesIO(display))
    thumb_img = Image.open(BytesIO(thumb))
    assert max(display_img.size) <= DISPLAY_MAX
    assert max(thumb_img.size) <= THUMB_MAX
    assert display_img.format == "JPEG"
    assert len(thumb) < len(original)
    assert b"Exif" not in display


def test_alembic_upgrades_legacy_sqlite(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    conn = sqlite3.connect(tmp_path / "eshop.db")
    conn.executescript(
        """
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            image_url TEXT NOT NULL,
            category TEXT NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            shipping_address TEXT NOT NULL,
            total_cents INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity INTEGER NOT NULL,
            unit_price_cents INTEGER NOT NULL
        );
        INSERT INTO products (slug, name, description, price_cents, image_url, category, stock)
        VALUES ('legacy-mug', 'Legacy Mug', 'Old row', 500, '/static/images/products/placeholder.svg', '3D Prints', 1);
        """
    )
    conn.close()
    init_schema()
    conn = sqlite3.connect(db_path())
    product_cols = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
    order_cols = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
    item_cols = {row[1] for row in conn.execute("PRAGMA table_info(order_items)")}
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "hidden" in product_cols
    assert "shipping_method" in order_cols
    assert "product_name" in item_cols
    assert "product_images" in tables
    assert "alembic_version" in tables
    version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert version == "006_product_genres"
    leftover = conn.execute("SELECT category FROM products WHERE slug = 'legacy-mug'").fetchone()
    assert leftover[0] == "Household"
    assert "archived" in order_cols
    assert "code" in product_cols
    assert "product_code" in item_cols
    gallery = conn.execute("SELECT url FROM product_images WHERE product_id = 1").fetchone()
    assert gallery is not None
    conn.close()


def test_admin_upload_uses_thumb_on_catalog(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_schema()
    seed_products()
    client = TestClient(app)
    client.post("/admin/login", data={"password": "printmemaybe"})
    payload = _jpeg_bytes(1800, 1200)
    created = client.post(
        "/admin/products",
        data={
            "name": "Large Photo Print",
            "description": "Resized upload.",
            "price": "9.00",
            "category": "Household",
            "stock": "2",
        },
        files={"images": ("huge.jpg", payload, "image/jpeg")},
        follow_redirects=False,
    )
    assert created.status_code == 303
    product = next(p for p in list_all_products() if p.slug == "large-photo-print")
    assert product.image_url.startswith("/media/products/")
    assert product.image_url.endswith(".jpg")
    assert "-thumb" not in Path(product.image_url).stem
    assert product.thumb_url.endswith("-thumb.jpg")
    display = client.get(product.image_url)
    thumb = client.get(product.thumb_url)
    assert display.status_code == 200
    assert thumb.status_code == 200
    assert display.content[:2] == b"\xff\xd8"
    assert len(thumb.content) < len(payload)
    assert max(Image.open(BytesIO(thumb.content)).size) <= THUMB_MAX
    home = client.get("/")
    assert product.thumb_url in home.text
    assert product.image_url not in home.text
    folder = product_images_dir()
    assert any(path.name.endswith("-thumb.jpg") for path in folder.iterdir())


def test_htmx_stock_qty_returns_card_not_full_page(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_schema()
    seed_products()
    client = TestClient(app)
    client.post("/admin/login", data={"password": "printmemaybe"})
    glasses = next(p for p in list_all_products() if p.slug == "glasses-case")
    fragment = client.post(
        f"/admin/stock/{glasses.id}",
        data={"stock": "9"},
        headers={"HX-Request": "true"},
    )
    assert fragment.status_code == 200
    assert "admin-product-card" in fragment.text
    assert "<html" not in fragment.text.lower()
    assert 'value="9"' in fragment.text
    assert 'hx-post="/admin/stock/' in fragment.text
    full = client.post(
        f"/admin/stock/{glasses.id}",
        data={"stock": "8"},
        follow_redirects=False,
    )
    assert full.status_code == 303
    assert full.headers["location"].startswith("/admin/stock")
    hidden = client.post(
        f"/admin/products/{glasses.id}/hide",
        headers={"HX-Request": "true"},
    )
    assert hidden.status_code == 200
    assert "Hidden" in hidden.text
    assert "<html" not in hidden.text.lower()


def test_packing_slip_pdf_download(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_schema()
    seed_products()
    client = TestClient(app)
    products = client.get("/api/products").json()
    glasses = next(p for p in products if p["slug"] == "glasses-case")
    client.post("/cart/add", data={"product_id": glasses["id"], "quantity": 1})
    checkout = client.post(
        "/checkout",
        data={
            "customer_name": "Pdf Buyer",
            "customer_email": "pdf@example.com",
            "shipping_method": "pickup",
        },
    )
    order_id = int(checkout.text.split("#")[1].split("<")[0])
    guest = client.get(f"/admin/orders/{order_id}/print.pdf", follow_redirects=False)
    assert guest.status_code == 303
    client.post("/admin/login", data={"password": "printmemaybe"})
    pdf = client.get(f"/admin/orders/{order_id}/print.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content[:4] == b"%PDF"
    assert f"order-{order_id}-packing-slip.pdf" in pdf.headers.get("content-disposition", "")
    page = client.get(f"/admin/orders/{order_id}")
    assert "Download PDF" in page.text
    assert f"/admin/orders/{order_id}/print.pdf" in page.text
