"""Apply Alembic migrations to the shop SQLite database."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from src.db import ensure_data_dir

ROOT = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(ROOT))
    return cfg


def upgrade_schema() -> None:
    """Bring DATA_DIR/eshop.db to the latest Alembic revision."""
    ensure_data_dir()
    command.upgrade(alembic_config(), "head")
