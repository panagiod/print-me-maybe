"""Home eyebrow, leftover catalog labels, and 3D/LC product codes.

Revision ID: 009_shop_hardening
Revises: 008_shop_settings
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "009_shop_hardening"
down_revision = "008_shop_settings"
branch_labels = None
depends_on = None

DEFAULT_EYEBROW = "Print Me Maybe"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            """
            INSERT OR IGNORE INTO shop_settings (key, value)
            VALUES ('home_eyebrow', :eyebrow)
            """
        ),
        {"eyebrow": DEFAULT_EYEBROW},
    )

    toys = bind.execute(
        text("SELECT 1 FROM product_genres WHERE name = 'Toys' COLLATE NOCASE")
    ).fetchone()
    if toys:
        bind.execute(
            text(
                """
                UPDATE products SET category = 'Toys'
                WHERE slug IN ('articulated-dragon', 'dragon-egg', 'dragon-egg-set')
                  AND category = 'Lord of the Rings'
                """
            )
        )

    pokemon = bind.execute(
        text("SELECT 1 FROM product_genres WHERE name = 'Pokemon' COLLATE NOCASE")
    ).fetchone()
    if pokemon:
        bind.execute(
            text(
                """
                UPDATE products SET category = 'Pokemon'
                WHERE (slug = 'psyduck' OR lower(name) LIKE '%psyduck%')
                  AND category = 'Household'
                """
            )
        )

    prefixes = {
        row[0]: row[1]
        for row in bind.execute(text("SELECT name, code_prefix FROM product_genres")).fetchall()
    }
    leftover = bind.execute(
        text(
            """
            SELECT id, category, code FROM products
            WHERE code LIKE '3D-%' OR code LIKE 'LC-%'
            """
        )
    ).fetchall()
    for product_id, category, code in leftover:
        prefix = (prefixes.get(category) or "PMM").strip().upper() or "PMM"
        suffix = code.split("-", 1)[1] if "-" in (code or "") else (code or str(product_id))
        candidate = f"{prefix}-{suffix}"
        extra = 2
        while True:
            taken = bind.execute(
                text("SELECT id FROM products WHERE code = :code AND id != :id"),
                {"code": candidate, "id": product_id},
            ).fetchone()
            if not taken:
                break
            candidate = f"{prefix}-{suffix}-{extra}"
            extra += 1
            if extra > 99:
                candidate = f"{prefix}-{product_id:03d}"
                break
        bind.execute(
            text("UPDATE products SET code = :code WHERE id = :id"),
            {"code": candidate, "id": product_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DELETE FROM shop_settings WHERE key = 'home_eyebrow'"))
    bind.execute(
        text(
            """
            UPDATE products SET category = 'Lord of the Rings'
            WHERE slug IN ('articulated-dragon', 'dragon-egg', 'dragon-egg-set')
              AND category = 'Toys'
            """
        )
    )
