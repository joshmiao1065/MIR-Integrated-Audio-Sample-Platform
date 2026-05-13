from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from app.config import settings

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
