"""Alembic environment — SQLite file from DATA_DIR (src.db.db_path)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from src.db import db_path, ensure_data_dir

config = context.config


def _url() -> str:
    ensure_data_dir()
    return f"sqlite:///{db_path()}"


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
