import uuid

import asyncpg.connection as _asyncpg_conn
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.config import settings

# Per-process random base for prepared statement names.
# asyncpg uses a global _uid counter starting at 0 on each process start, but
# PgBouncer's server connections retain prepared statements across Railway restarts.
# A process-unique prefix ensures new statements never collide with leftovers from
# a previous process that used the same underlying PostgreSQL server connection.
_stmt_base = int(uuid.uuid4().hex[:12], 16)

def _unique_stmt_name(self: object, prefix: str) -> str:
    _asyncpg_conn._uid += 1
    return f"__{prefix}_{_stmt_base + _asyncpg_conn._uid:x}__"

_asyncpg_conn.Connection._get_unique_id = _unique_stmt_name  # type: ignore[method-assign]

# NullPool: each request opens/closes its own connection rather than sharing a pool.
# Required for PgBouncer transaction mode — a regular pool initialises all connections
# concurrently, causing asyncpg to create identically-named prepared statements on the
# same PgBouncer server connection → DuplicatePreparedStatementError.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
