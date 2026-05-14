import asyncio
import uuid
from logging.config import fileConfig

import asyncpg.connection as _asyncpg_conn
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from alembic import context

from app.config import settings
from app.models.base import Base
import app.models  # noqa: F401 — registers all ORM models with Base.metadata

# Same monkey-patch as database.py — prevents DuplicatePreparedStatementError
# when PgBouncer retains server connections across process restarts.
_stmt_base = int(uuid.uuid4().hex[:12], 16)

def _unique_stmt_name(self: object, prefix: str) -> str:
    _asyncpg_conn._uid += 1
    return f"__{prefix}_{_stmt_base + _asyncpg_conn._uid:x}__"

_asyncpg_conn.Connection._get_unique_id = _unique_stmt_name  # type: ignore[method-assign]

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
