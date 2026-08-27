"""Hidden products and photo gallery.

Revision ID: 003_catalog
Revises: 002_order_cols
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "003_catalog"
down_revision = "002_order_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {
        row[1]
        for row in op.get_bind().execute(text("PRAGMA table_info(products)")).fetchall()
    }
    if "hidden" not in cols:
        op.execute("ALTER TABLE products ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS product_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        """
        INSERT INTO product_images (product_id, url, sort_order)
        SELECT p.id, p.image_url, 0
        FROM products p
        WHERE p.image_url IS NOT NULL AND p.image_url != ''
          AND NOT EXISTS (
              SELECT 1 FROM product_images pi WHERE pi.product_id = p.id
          )
        """
    )


def downgrade() -> None:
    pass
