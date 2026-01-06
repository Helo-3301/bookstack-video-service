"""Database connection and session management."""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from bsvs.config import get_settings
from bsvs.db.base import Base  # noqa: F401

# Lazy initialization - engine and session are created on first use
_engine = None
_async_session = None


def _get_engine():
    """Get or create the async engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
        )
    return _engine


def _get_async_session():
    """Get or create the async session maker."""
    global _async_session
    if _async_session is None:
        _async_session = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session


# For backwards compatibility
engine = None  # Lazy, use _get_engine() for actual access


async def init_db():
    """Initialize the database, creating all tables."""
    from bsvs.db.models import Video, VideoVariant, TranscodeJob  # noqa: F401

    eng = _get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency."""
    async_session = _get_async_session()
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
