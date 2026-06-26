import asyncio
from collections.abc import Callable, Coroutine
from urllib.parse import quote_plus

import asyncpg
import boto3

from api.v1.utils.config import config


def _generate_iam_token(host: str) -> str:
    """
    Generates a short-lived IAM authentication token for the given Aurora host.
    Tokens expire after 15 minutes — never cache; generate fresh for every new
    physical connection, whether it is to the writer or a reader endpoint.
    """
    client = boto3.client("rds", region_name=config.AWS_REGION)
    return client.generate_db_auth_token(
        DBHostname=host,
        Port=config.DB_PORT,
        DBUsername=config.DB_USERNAME,
        Region=config.AWS_REGION,
    )


def iam_connection_factory(host: str) -> Callable[[], Coroutine[None, None, asyncpg.Connection]]:
    """
    Returns an async_creator callable bound to the given Aurora endpoint.

    Aurora clusters expose two DNS names: a writer endpoint and one or more
    reader endpoints. Both require IAM auth — the only difference is the hostname
    used to generate the presigned token and to open the TCP connection. This
    factory lets database.py build independent pooled engines for each endpoint
    without duplicating the token-refresh logic.

    The returned coroutine is called by the SQLAlchemy connection pool every time
    it opens a brand-new physical connection, so each one authenticates with a
    token that was minted at that exact moment rather than reusing a token from
    engine startup.
    """
    async def _create_connection() -> asyncpg.Connection:
        token = await asyncio.to_thread(_generate_iam_token, host)
        return await asyncpg.connect(
            host=host,
            port=config.DB_PORT,
            user=config.DB_USERNAME,
            password=token,
            database=config.DB_NAME,
            ssl="require",
        )

    return _create_connection


# ── Convenience aliases used by database.py and migrate.py ───────────────────

async def create_iam_connection() -> asyncpg.Connection:
    """Writer endpoint. Kept for backward-compatibility with migrate.py."""
    return await iam_connection_factory(config.DB_HOST)()


def build_database_url() -> str:
    """
    Builds a full asyncpg-compatible connection URL using a fresh IAM token.
    Intended for short-lived, single-connection contexts (Alembic migrations).

    For the long-lived pooled engine, use iam_connection_factory() via
    create_async_engine's async_creator instead — a connection string with a
    baked-in token would go stale for any connection the pool opens more than
    15 minutes after engine creation.

    The token contains '?', '&', and '=' characters and is percent-encoded
    before being embedded as the password component. sslmode=require is mandatory
    for Aurora.
    """
    token = _generate_iam_token(config.DB_HOST)
    encoded_token = quote_plus(token, safe="")
    return (
        f"postgresql+asyncpg://{config.DB_USERNAME}:{encoded_token}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
        f"?ssl=require"
    )
