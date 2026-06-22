import asyncio
from urllib.parse import quote_plus

import asyncpg
import boto3

from api.v1.utils.config import config


def _generate_iam_token() -> str:
    """
    Generates a short-lived IAM authentication token for Aurora PostgreSQL.
    Tokens expire after 15 minutes — never cache this value, generate a fresh
    one for every new physical connection.
    """
    client = boto3.client("rds", region_name=config.AWS_REGION)
    return client.generate_db_auth_token(
        DBHostname=config.DB_HOST,
        Port=config.DB_PORT,
        DBUsername=config.DB_USERNAME,
        Region=config.AWS_REGION,
    )


async def generate_iam_token() -> str:
    """boto3 is sync; offloaded to a thread so it never blocks the event loop."""
    return await asyncio.to_thread(_generate_iam_token)


def build_database_url() -> str:
    """
    Builds a full asyncpg-compatible connection URL using a fresh IAM token.
    Intended for short-lived, single-connection contexts (Alembic migrations,
    the migrate.py script) where one token comfortably outlives the whole run.

    For the long-lived pooled engine, use create_iam_connection() (below) via
    create_async_engine's async_creator instead — a connection string with a
    baked-in token would go stale for any connection the pool opens more than
    15 minutes after engine creation.

    The token itself is a presigned-URL-shaped string containing '?', '&', and
    '=' characters, so it's percent-encoded before being embedded as the
    password component — otherwise it would corrupt the URL. sslmode=require
    is mandatory for Aurora express configuration clusters.
    """
    token = _generate_iam_token()
    encoded_token = quote_plus(token, safe="")
    return (
        f"postgresql+asyncpg://{config.DB_USERNAME}:{encoded_token}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
        f"?ssl=require"
    )


async def create_iam_connection() -> asyncpg.Connection:
    """
    async_creator hook for create_async_engine — called by the connection pool
    every time it opens a brand-new physical connection (including ones opened
    well after startup, e.g. after pool_recycle or under load), so each one
    authenticates with a token generated at that moment rather than reusing
    whatever token existed when the engine was first created.
    """
    token = await generate_iam_token()
    return await asyncpg.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USERNAME,
        password=token,
        database=config.DB_NAME,
        ssl="require",
    )
