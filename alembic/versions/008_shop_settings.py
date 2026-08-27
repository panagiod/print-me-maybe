"""Shop home title and banner in SQLite so studio can edit them.

Revision ID: 008_shop_settings
Revises: 007_genre_table
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "008_shop_settings"
down_revision = "007_genre_table"
branch_labels = None
depends_on = None

HOME_TITLE = "Personalized 3D prints,\nmade to order."
HOME_BANNER = (
    "Baby gifts, keepsakes, fandom décor, household pieces, and toys from "
    "@print.me.maybe — Harry Potter, Lord of the Rings, household, Pokémon, "
    "and toys. Made in Cyprus. Free pick up; €3.50 delivery in Cyprus; "
    "€10 delivery in Greece."
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shop_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    bind = op.get_bind()
    bind.execute(
        text(
            """
            INSERT OR IGNORE INTO shop_settings (key, value)
            VALUES ('home_title', :title), ('home_banner', :banner)
            """
        ),
        {"title": HOME_TITLE, "banner": HOME_BANNER},
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shop_settings")
