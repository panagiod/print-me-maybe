"""Remap catalog from 3D/laser lines to fandom and household genres.

Revision ID: 006_product_genres
Revises: 005_product_code
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "006_product_genres"
down_revision = "005_product_code"
branch_labels = None
depends_on = None

GENRES_BY_SLUG = {
    "magical-world-bookshelf": "Harry Potter",
    "magic-bookshelf-decor": "Harry Potter",
    "minas-tirith": "Lord of the Rings",
    "articulated-dragon": "Lord of the Rings",
    "dragon-egg": "Lord of the Rings",
    "dragon-egg-set": "Lord of the Rings",
    "glasses-case": "Household",
    "scrunchie-holder": "Household",
    "lip-balm-holder-set": "Household",
    "funny-desk-signs": "Household",
    "custom-cake-topper": "Household",
    "bear-keychain": "Household",
    "oak-coaster-set": "Household",
    "cutting-board": "Household",
    "name-plaque": "Household",
    "family-name-sign": "Household",
}


def upgrade() -> None:
    bind = op.get_bind()
    for slug, genre in GENRES_BY_SLUG.items():
        bind.execute(
            text("UPDATE products SET category = :genre WHERE slug = :slug"),
            {"genre": genre, "slug": slug},
        )
    bind.execute(
        text(
            "UPDATE products SET category = 'Household' "
            "WHERE category IN ('3D Prints', 'Laser Engraving')"
        )
    )


def downgrade() -> None:
    pass
