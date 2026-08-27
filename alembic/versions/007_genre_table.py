"""Store shop genres in SQLite so studio can add, rename, and remove them.

Revision ID: 007_genre_table
Revises: 006_product_genres
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "007_genre_table"
down_revision = "006_product_genres"
branch_labels = None
depends_on = None

DEFAULT_GENRES = (
    ("Harry Potter", "HP", 10),
    ("Lord of the Rings", "LOTR", 20),
    ("Household", "HH", 30),
    ("Pokemon", "PK", 40),
    ("Toys", "TOY", 50),
)
LEGACY_PREFIXES = {"3D Prints": "3D", "Laser Engraving": "LC"}


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS product_genres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code_prefix TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_product_genres_name "
        "ON product_genres(name COLLATE NOCASE)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_product_genres_prefix "
        "ON product_genres(code_prefix COLLATE NOCASE)"
    )
    bind = op.get_bind()
    for name, prefix, sort_order in DEFAULT_GENRES:
        bind.execute(
            text(
                """
                INSERT INTO product_genres (name, code_prefix, sort_order)
                SELECT :name, :prefix, :sort_order
                WHERE NOT EXISTS (
                    SELECT 1 FROM product_genres WHERE name = :name COLLATE NOCASE
                )
                """
            ),
            {"name": name, "prefix": prefix, "sort_order": sort_order},
        )
    used_prefixes = {prefix.upper() for _, prefix, _ in DEFAULT_GENRES}
    extra = bind.execute(text("SELECT DISTINCT category FROM products")).fetchall()
    sort_order = 60
    for (category,) in extra:
        name = (category or "").strip()
        if not name:
            continue
        exists = bind.execute(
            text("SELECT 1 FROM product_genres WHERE name = :name COLLATE NOCASE"),
            {"name": name},
        ).fetchone()
        if exists:
            continue
        prefix = LEGACY_PREFIXES.get(name, "")
        if not prefix:
            prefix = "".join(ch for ch in name.upper() if ch.isalnum())[:4] or "PMM"
        base = prefix
        extra_n = 2
        while prefix.upper() in used_prefixes:
            prefix = f"{base}{extra_n}"[:8]
            extra_n += 1
        used_prefixes.add(prefix.upper())
        bind.execute(
            text(
                "INSERT INTO product_genres (name, code_prefix, sort_order) "
                "VALUES (:name, :prefix, :sort_order)"
            ),
            {"name": name, "prefix": prefix, "sort_order": sort_order},
        )
        sort_order += 10


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_product_genres_prefix")
    op.execute("DROP INDEX IF EXISTS idx_product_genres_name")
    op.execute("DROP TABLE IF EXISTS product_genres")
