"""Async SQLAlchemy engine and transaction dependencies."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings


def _async_database_url(url: str) -> str:
    """Normalize a PostgreSQL URL for psycopg's async SQLAlchemy dialect."""

    if url.startswith("postgresql+psycopg://"):
        return url
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


@lru_cache
def get_engine() -> AsyncEngine:
    """Create the canonical database engine once per process."""

    settings = get_settings()
    return create_async_engine(
        _async_database_url(settings.database.resolved_url()),
        pool_pre_ping=True,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        connect_args={"options": f"-c statement_timeout={settings.database.statement_timeout_ms}"},
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create the reusable async session factory."""

    return async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)


async def session_dependency() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session and roll back uncommitted failures."""

    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def database_ready() -> bool:
    """Return whether PostgreSQL accepts a simple query."""

    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
