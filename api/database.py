from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from api.v1.utils.config import config
from api.v1.utils.logger import get_logger

logger = get_logger("database")


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    config.DATABASE_URL,
    pool_size=config.DB_POOL_SIZE,
    max_overflow=config.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def connect() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)
    logger.info("Database connected", extra={"url": config.DATABASE_URL.split("@")[-1]})


async def disconnect() -> None:
    await engine.dispose()
    logger.info("Database disconnected")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
