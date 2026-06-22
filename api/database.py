from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from api.v1.services.db_auth import create_iam_connection
from api.v1.utils.config import config
from api.v1.utils.logger import get_logger

logger = get_logger("database")


class Base(DeclarativeBase):
    pass


def _build_engine() -> AsyncEngine:
    # pool_recycle=600 forces connections to be discarded and reopened every
    # 10 minutes, comfortably inside the 15-minute IAM token lifetime — but it
    # only protects connections the pool reuses, not ones it opens fresh.
    # That's why the IAM branch uses async_creator (create_iam_connection)
    # rather than a static URL with a token baked in: a fresh token is minted
    # for every new physical connection, no matter when the pool opens it.
    if config.DB_HOST:
        return create_async_engine(
            "postgresql+asyncpg://",
            async_creator=create_iam_connection,
            pool_size=config.DB_POOL_SIZE,
            max_overflow=config.DB_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=600,
            echo=False,
        )
    return create_async_engine(
        config.DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=600,
        echo=False,
    )


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def connect() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)
    target = f"{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}" if config.DB_HOST else config.DATABASE_URL.split("@")[-1]
    logger.info("Database connected", extra={"url": target})


async def disconnect() -> None:
    await engine.dispose()
    logger.info("Database disconnected")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
