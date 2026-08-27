"""SQLite database helpers — file-backed store for products and orders."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

# Default path works locally; production sets DATA_DIR to a real disk (Hetzner: /var/lib/eshop).
def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/tmp/eshop-data"))


def data_persistent() -> bool:
    """False when SQLite lives under /tmp (wiped on reboot / Render Free)."""
    return not str(data_dir()).startswith("/tmp")


def db_path() -> Path:
    return data_dir() / "eshop.db"


def ensure_data_dir() -> None:
    """Create the data directory before opening SQLite (containers use read-only root)."""
    data_dir().mkdir(parents=True, exist_ok=True)


def product_images_dir() -> Path:
    """Writable folder for photos uploaded from the admin stock page."""
    path = data_dir() / "product-images"
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Yield a connection with row dict access and foreign keys enabled."""
    ensure_data_dir()
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema() -> None:
    """Apply Alembic migrations so this process matches the current schema."""
    from src.migrate import upgrade_schema

    upgrade_schema()


def sync_product_image_gallery() -> None:
    """Backfill gallery rows for products that only have image_url (e.g. after seed)."""
    with get_connection() as conn:
        conn.execute(
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
