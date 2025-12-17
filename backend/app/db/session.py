# app/db/session.py
"""
Database session and initialization utilities.

We use:
- SQLAlchemy async engine + AsyncSession
- SQLite via aiosqlite driver (works great for MVP + local deployments)

Key points:
- `init_db()` creates tables and applies SQLite pragmas for performance.
- `get_session()` is a FastAPI dependency that yields an AsyncSession.
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Base


# Create an async engine. Keep echo=False to avoid logging SQL in normal use.
# If you want to debug SQL, set echo=True temporarily (or gate it behind ENV).
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

# Session factory used by FastAPI dependencies and services.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,  # prevents attributes from expiring after commit (less surprising)
    class_=AsyncSession,
)


def _sync_database_url(url: str) -> str:
    """
    Convert the async SQLite URL (sqlite+aiosqlite:///) into a sync-friendly URL.
    """
    if url.startswith("sqlite+aiosqlite"):
        return "sqlite" + url[len("sqlite+aiosqlite") :]
    return url


# Synchronous engine/session for background tasks or utilities that cannot await.
sync_engine = create_engine(
    _sync_database_url(settings.DATABASE_URL),
    echo=False,
    future=True,
)
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
    class_=Session,
)


async def init_db() -> None:
    """
    Initialize database schema and apply SQLite pragmas.

    Pragmas rationale:
    - journal_mode=WAL: better concurrency (reads don't block writes as often)
    - synchronous=NORMAL: good balance for durability vs speed for this MVP
    - foreign_keys=ON: enforce FK constraints (future-proofing)
    """
    async with engine.begin() as conn:
        # SQLite performance & correctness pragmas
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.execute(text("PRAGMA synchronous=NORMAL;"))
        await conn.execute(text("PRAGMA foreign_keys=ON;"))

        # Create tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a scoped AsyncSession.

    Usage:
        @router.get(...)
        async def handler(session: AsyncSession = Depends(get_session)):
            ...

    Ensures:
    - session is always closed
    - transactions are controlled explicitly in route/service logic
    """
    async with AsyncSessionLocal() as session:
        yield session
