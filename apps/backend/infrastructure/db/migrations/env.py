"""Alembic environment that loads DB URL from `apps.backend.infrastructure.platform.config`.

This file configures Alembic to run SQL migrations stored under
`migrations/sql/*.sql`. The `sqlalchemy.url` option is set from
`apps.backend.infrastructure.platform.config.config.DATABASE_URL` so you don't need to edit
`alembic.ini` with credentials.
"""
from __future__ import annotations

import sys
from pathlib import Path

from logging.config import fileConfig

from alembic import context

# Repository root (migrations → … → apps → repo root).
ROOT = str(Path(__file__).resolve().parents[5])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from apps.backend.infrastructure.platform.config import config as app_config  # type: ignore

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# override sqlalchemy.url from app config (psycopg3 driver, not default psycopg2)
if getattr(app_config, "DATABASE_URL", None):
    config.set_main_option(
        "sqlalchemy.url",
        getattr(app_config, "SQLALCHEMY_DATABASE_URL", None) or app_config.DATABASE_URL,
    )

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine, though
    an Engine is acceptable here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we create an Engine and associate a connection with the
    context.
    """
    from sqlalchemy import create_engine

    connectable = create_engine(config.get_main_option("sqlalchemy.url"))

    with connectable.connect() as connection:
        context.configure(connection=connection)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
