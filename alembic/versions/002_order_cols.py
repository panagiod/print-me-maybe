"""Order fulfillment columns, lookup tokens, shipping backfill.

Revision ID: 002_order_cols
Revises: 001_baseline
Create Date: 2026-08-27
"""

from __future__ import annotations

import secrets

from alembic import op
from sqlalchemy import text

revision = "002_order_cols"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    rows = op.get_bind().execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _add_text(table: str, column: str, default: str = "") -> None:
    if column not in _columns(table):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT '{default}'"
        )


def upgrade() -> None:
    for name in (
        "status",
        "notes",
        "lookup_token",
        "payment_status",
        "shipping_method",
        "delivery_country",
        "tracking_number",
        "customer_notes",
        "customer_phone",
        "payment_method",
    ):
        if name == "status":
            if "status" not in _columns("orders"):
                op.execute("ALTER TABLE orders ADD COLUMN status TEXT NOT NULL DEFAULT 'new'")
        elif name == "payment_status":
            if "payment_status" not in _columns("orders"):
                op.execute(
                    "ALTER TABLE orders ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'unpaid'"
                )
        elif name == "lookup_token":
            if "lookup_token" not in _columns("orders"):
                op.execute("ALTER TABLE orders ADD COLUMN lookup_token TEXT")
        else:
            _add_text("orders", name)

    if "product_name" not in _columns("order_items"):
        op.execute(
            "ALTER TABLE order_items ADD COLUMN product_name TEXT NOT NULL DEFAULT ''"
        )
        op.execute(
            """
            UPDATE order_items SET product_name = (
                SELECT name FROM products WHERE products.id = order_items.product_id
            )
            WHERE product_name = '' OR product_name IS NULL
            """
        )

    pending_cols = _columns("pending_checkouts")
    if pending_cols:
        if "customer_notes" not in pending_cols:
            op.execute(
                "ALTER TABLE pending_checkouts ADD COLUMN customer_notes TEXT NOT NULL DEFAULT ''"
            )
        if "customer_phone" not in pending_cols:
            op.execute(
                "ALTER TABLE pending_checkouts ADD COLUMN customer_phone TEXT NOT NULL DEFAULT ''"
            )

    conn = op.get_bind()
    missing = conn.execute(
        text("SELECT id FROM orders WHERE lookup_token IS NULL OR lookup_token = ''")
    ).fetchall()
    for row in missing:
        conn.execute(
            text("UPDATE orders SET lookup_token = :token WHERE id = :id"),
            {"token": secrets.token_urlsafe(16), "id": row[0]},
        )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_lookup_token ON orders(lookup_token)"
    )

    rows = conn.execute(
        text(
            """
            SELECT id, shipping_address, total_cents, shipping_method FROM orders
            WHERE shipping_method IS NULL OR shipping_method = ''
            """
        )
    ).fetchall()
    for row in rows:
        order_id, address, total_cents, _method = row[0], row[1], row[2], row[3]
        address = (address or "").strip()
        if address.lower().startswith("pick up"):
            conn.execute(
                text(
                    "UPDATE orders SET shipping_method = 'pickup', delivery_country = '' WHERE id = :id"
                ),
                {"id": order_id},
            )
            continue
        item_total = conn.execute(
            text(
                "SELECT COALESCE(SUM(quantity * unit_price_cents), 0) FROM order_items WHERE order_id = :id"
            ),
            {"id": order_id},
        ).scalar()
        shipping = max(0, int(total_cents) - int(item_total or 0))
        country = "other" if shipping >= 1000 else "cyprus"
        conn.execute(
            text(
                "UPDATE orders SET shipping_method = 'delivery', delivery_country = :country WHERE id = :id"
            ),
            {"country": country, "id": order_id},
        )


def downgrade() -> None:
    pass
