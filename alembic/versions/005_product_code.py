"""Product codes on catalog and order lines.

Revision ID: 005_product_code
Revises: 004_order_archive
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "005_product_code"
down_revision = "004_order_archive"
branch_labels = None
depends_on = None

SEED_CODES = {
    "magical-world-bookshelf": "3D-BOOKSHELF",
    "glasses-case": "3D-GLASSES",
    "scrunchie-holder": "3D-SCRUNCHIE",
    "lip-balm-holder-set": "3D-LIPBALM",
    "magic-bookshelf-decor": "3D-WIZARD",
    "minas-tirith": "3D-MINAS",
    "funny-desk-signs": "3D-SIGNS",
    "articulated-dragon": "3D-DRAGON",
    "dragon-egg": "3D-EGG",
    "dragon-egg-set": "3D-SET",
    "custom-cake-topper": "3D-TOPPER",
    "bear-keychain": "3D-BEAR",
    "oak-coaster-set": "LC-COASTERS",
    "cutting-board": "LC-BOARD",
    "name-plaque": "LC-PLAQUE",
    "family-name-sign": "LC-SIGN",
}


def upgrade() -> None:
    bind = op.get_bind()
    product_cols = {
        row[1] for row in bind.execute(text("PRAGMA table_info(products)")).fetchall()
    }
    item_cols = {
        row[1] for row in bind.execute(text("PRAGMA table_info(order_items)")).fetchall()
    }
    if "code" not in product_cols:
        op.execute("ALTER TABLE products ADD COLUMN code TEXT NOT NULL DEFAULT ''")
    if "product_code" not in item_cols:
        op.execute("ALTER TABLE order_items ADD COLUMN product_code TEXT NOT NULL DEFAULT ''")

    for slug, code in SEED_CODES.items():
        bind.execute(
            text("UPDATE products SET code = :code WHERE slug = :slug AND COALESCE(code, '') = ''"),
            {"code": code, "slug": slug},
        )
    op.execute(
        """
        UPDATE products
        SET code = CASE
            WHEN category = 'Laser Engraving' THEN printf('LC-%03d', id)
            ELSE printf('3D-%03d', id)
        END
        WHERE COALESCE(code, '') = ''
        """
    )
    op.execute(
        """
        UPDATE order_items
        SET product_code = COALESCE(
            (SELECT code FROM products WHERE products.id = order_items.product_id),
            ''
        )
        WHERE COALESCE(product_code, '') = ''
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_products_code ON products(code) WHERE code != ''"
    )


def downgrade() -> None:
    pass
