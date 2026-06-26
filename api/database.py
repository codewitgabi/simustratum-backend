from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from api.v1.services.db_auth import create_iam_connection, iam_connection_factory
from api.v1.utils.config import config
from api.v1.utils.logger import get_logger

logger = get_logger("database")


class Base(DeclarativeBase):
    pass


def _build_engine(*, reader: bool = False) -> AsyncEngine:
    """
    Builds an async SQLAlchemy engine for either the Aurora writer or reader endpoint.

    Aurora exposes two DNS names: a writer endpoint that always points to the
    primary instance, and a reader endpoint that load-balances across read replicas.
    Routing read-only queries (session list, replay, billing status) to the reader
    offloads the primary and gives replicas a reason to exist beyond failover.

    pool_recycle=600 forces connections to be discarded and reopened every 10 minutes,
    comfortably inside the 15-minute IAM token lifetime — but this only protects
    connections the pool *reuses*. That is why IAM paths use async_creator
    (iam_connection_factory) rather than a static URL with a baked-in token: a
    fresh token is minted for every new physical connection, regardless of when the
    pool decides to open it.

    pool_pre_ping=True sends a lightweight "SELECT 1" before handing a connection
    to application code. Aurora Serverless v2 can pause and resume, and pre-ping
    catches stale connections that survived pool_recycle but hit a pause window.
    """
    _shared_pool_kwargs = dict(
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        pool_timeout=config.DB_POOL_TIMEOUT,
        pool_pre_ping=True,
        pool_recycle=600,
        echo=False,
    )

    if config.DB_HOST:
        # IAM path: determine which Aurora endpoint to target.
        #   writer: DB_HOST (cluster endpoint — always routes to the primary)
        #   reader: DB_READER_HOST if set, otherwise fall back to writer so that
        #           single-instance deploys and local dev need zero extra config.
        if reader and config.DB_READER_HOST:
            creator = iam_connection_factory(config.DB_READER_HOST)
            logger.info("Building reader engine", extra={"host": config.DB_READER_HOST})
        else:
            creator = iam_connection_factory(config.DB_HOST)

        return create_async_engine(
            "postgresql+asyncpg://",
            async_creator=creator,
            **_shared_pool_kwargs,
        )

    # Local / non-Aurora path: plain DATABASE_URL.
    return create_async_engine(
        config.DATABASE_URL,
        **_shared_pool_kwargs,
    )


engine = _build_engine()
reader_engine = _build_engine(reader=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

_ReaderSessionLocal = async_sessionmaker(
    bind=reader_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def connect() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)
    target = f"{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}" if config.DB_HOST else config.DATABASE_URL.split("@")[-1]
    reader_target = config.DB_READER_HOST or "(same as writer)"
    logger.info("Database connected", extra={"writer": target, "reader": reader_target})


async def disconnect() -> None:
    await engine.dispose()
    await reader_engine.dispose()
    logger.info("Database disconnected")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Writer session — use for all INSERT / UPDATE / DELETE operations."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_read_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Reader session — routes to the Aurora reader endpoint when DB_READER_HOST is
    configured, otherwise identical to get_db (same writer engine).

    Use this for read-only operations: session lists, replays, billing status
    reads. Never use it for anything that mutates state — the reader endpoint
    points to a replica, and writes will fail at the database level.
    """
    async with _ReaderSessionLocal() as session:
        yield session
