"""Move dragon SKUs from Lord of the Rings to Toys.

Revision ID: 007_dragon_toys
Revises: 006_product_genres
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "007_dragon_toys"
down_revision = "006_product_genres"
branch_labels = None
depends_on = None

DRAGON_SLUGS = ("articulated-dragon", "dragon-egg", "dragon-egg-set")


def upgrade() -> None:
    bind = op.get_bind()
    for slug in DRAGON_SLUGS:
        bind.execute(
            text("UPDATE products SET category = 'Toys' WHERE slug = :slug"),
            {"slug": slug},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for slug in DRAGON_SLUGS:
        bind.execute(
            text("UPDATE products SET category = 'Lord of the Rings' WHERE slug = :slug"),
            {"slug": slug},
        )
