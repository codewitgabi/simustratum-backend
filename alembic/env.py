import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from api.database import Base
from api.v1.services.db_auth import build_database_url
from api.v1.utils.config import config as app_config
import api.v1.models  # noqa: F401 — ensures all models are registered with Base

alembic_config = context.config
# A single token comfortably outlives a migration run, so build_database_url()
# (one IAM token minted up front) is fine here — unlike the pooled app engine,
# which needs a fresh token per connection over its much longer lifetime.
_database_url = build_database_url() if app_config.DB_HOST else app_config.DATABASE_URL
# alembic_config is backed by ConfigParser, which treats '%' as interpolation
# syntax — the IAM token is percent-encoded (full of literal '%XX' sequences),
# so '%' must be doubled to '%%' or set_main_option raises ValueError.
alembic_config.set_main_option("sqlalchemy.url", _database_url.replace("%", "%%"))

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
