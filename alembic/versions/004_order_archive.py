"""Archive flag on orders.

Revision ID: 004_order_archive
Revises: 003_catalog
Create Date: 2026-08-27
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "004_order_archive"
down_revision = "003_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {
        row[1]
        for row in op.get_bind().execute(text("PRAGMA table_info(orders)")).fetchall()
    }
    if "archived" not in cols:
        op.execute("ALTER TABLE orders ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    pass
