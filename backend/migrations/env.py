"""Alembic migration environment.

Reads the DB URL from the DATABASE_URL env var (never hardcoded) and uses the
app's SQLAlchemy metadata so `--autogenerate` can diff models → migrations.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# Make the repo root importable so `backend.*` resolves when alembic runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.database import Base  # noqa: E402
from backend import models  # noqa: E402,F401  (register models on Base.metadata)

config = context.config

# The runtime DATABASE_URL (env wins over anything in the ini).
#
# NEVER put this through `config.set_main_option`. Alembic's config is a
# ConfigParser, which treats `%` as interpolation syntax — and the Claritty
# platform hands every app a URL of the form
#
#     …/clarity_platform?options=-csearch_path%3Dtenant_<id>&sslmode=require
#
# so the `%3D` (a URL-encoded `=`, pinning the tenant's schema) makes
# set_main_option raise `ValueError: invalid interpolation syntax`. Alembic
# dies before a single migration runs, the container never comes up healthy,
# and the platform reports it as "Build failed. Please check that your app
# builds successfully locally" — which it does, because a local DATABASE_URL
# has no `%` in it and the crash is invisible until you run against a
# tenant-scoped database.
_db_url = os.getenv("DATABASE_URL")

if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        pass

target_metadata = Base.metadata


def _url() -> str:
    """The URL to migrate against, taken raw so `%` is never interpolated."""
    return _db_url or config.get_main_option("sqlalchemy.url") or ""


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # create_engine, not engine_from_config: the latter reads back through the
    # ConfigParser section and would re-introduce the `%` interpolation problem
    # even if the value got in by another route.
    connectable = create_engine(_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
