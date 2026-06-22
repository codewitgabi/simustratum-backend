import os

_DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/simustratum_test"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)
# Force the plain-DATABASE_URL path regardless of what a developer's real .env
# has configured for Aurora IAM auth — tests must never attempt a real AWS
# connection, and must be deterministic across machines.
os.environ["DB_HOST"] = ""
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-integration-tests")
os.environ.setdefault("JWT_ACCESS_EXPIRE_MINUTES", "15")
os.environ.setdefault("JWT_REFRESH_EXPIRE_DAYS", "30")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("CLOUDINARY_URL", "cloudinary://test_key:test_secret@test_cloud")
os.environ.setdefault("GOOGLE_CLIENT_ID", "")
os.environ.setdefault("ALLOWED_ORIGINS", "")

import uuid
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import api.database as database_module
from api.v1.utils.config import config

REPO_ROOT = Path(__file__).resolve().parent.parent


def _sync_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _admin_dsn(database_url: str) -> str:
    parsed = urlparse(_sync_dsn(database_url))
    return f"postgresql://{parsed.netloc}/postgres"


def _target_db_name(database_url: str) -> str:
    return urlparse(_sync_dsn(database_url)).path.lstrip("/")


def _ensure_test_database_exists() -> None:
    db_name = _target_db_name(config.DATABASE_URL)
    conn = psycopg2.connect(_admin_dsn(config.DATABASE_URL))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        conn.close()


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    """Creates (if needed) and migrates the dedicated test database once per run."""
    _ensure_test_database_exists()
    _run_migrations()

    # Swap the app's module-level engine/sessionmaker for NullPool versions:
    # the WebSocket tests use Starlette's TestClient, which runs the ASGI app on a
    # separate thread with its own event loop. asyncpg connections are bound to the
    # loop that created them, so a pooled connection checked out on one loop and
    # reused on another raises. NullPool opens a fresh connection per checkout/
    # release, sidestepping that entirely — at the cost of pooling, which is fine
    # for a test suite.
    database_module.engine = create_async_engine(config.DATABASE_URL, poolclass=NullPool, echo=False)
    database_module.AsyncSessionLocal = async_sessionmaker(
        bind=database_module.engine, expire_on_commit=False, class_=AsyncSession
    )


def _truncate_all_tables() -> None:
    conn = psycopg2.connect(_sync_dsn(config.DATABASE_URL))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public' AND tablename != 'alembic_version'
                """
            )
            tables = [row[0] for row in cur.fetchall()]
            if tables:
                quoted = ", ".join(f'"{t}"' for t in tables)
                cur.execute(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _clean_database() -> Iterator[None]:
    """Each test starts against an empty schema — isolation without per-test transactions."""
    yield
    _truncate_all_tables()


@pytest.fixture(autouse=True)
def _clean_orchestrator_registry() -> Iterator[None]:
    """SessionOrchestrator instances live in a module-level dict keyed by session_id (a
    real session UUID per test), so leaking between tests isn't actually possible —
    cleared anyway for safety since the dict would otherwise grow unbounded across a run."""
    from api.v1.services.session_orchestrator import _registry

    yield
    _registry.clear()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    httpx AsyncClient over the real ASGI app, in-process, no running server. Lifespan
    is intentionally NOT triggered (ASGITransport doesn't send lifespan events unless
    asked to) — that's what would otherwise fire a real Qdrant connectivity check on
    startup; nothing under test depends on it.
    """
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


class FakeQdrantClient:
    """In-memory stand-in for AsyncQdrantClient — used wherever a test exercises a
    code path that touches Qdrant, instead of hitting a real instance."""

    def __init__(self) -> None:
        self._points: dict[str, list] = {}

    async def collection_exists(self, name: str) -> bool:
        return True

    async def create_collection(self, **kwargs) -> None:
        pass

    async def create_payload_index(self, **kwargs) -> None:
        pass

    async def get_collections(self):
        from types import SimpleNamespace

        return SimpleNamespace(collections=[])

    async def upsert(self, collection_name: str, points: list) -> None:
        self._points.setdefault(collection_name, []).extend(points)

    async def query_points(self, collection_name: str, query, query_filter, limit: int):
        from types import SimpleNamespace

        document_id = query_filter.must[0].match.value
        matches = [
            p for p in self._points.get(collection_name, []) if p.payload.get("document_id") == document_id
        ][:limit]
        return SimpleNamespace(points=matches)

    async def close(self) -> None:
        pass


@pytest.fixture
def stub_external_services(monkeypatch) -> None:
    """
    Opt-in stub for the genuinely external network calls (Gemini generation/
    embeddings, Qdrant, Cloudinary's upload, Anthropic). Each function is imported
    by reference into the modules that call it (not looked up dynamically), so the
    patch target is the *importing* module's namespace, not the defining module's.

    Does not touch `score_response` (no network call — it's a local placeholder) or
    `_verify_google_id_token` (only relevant to the google-auth tests, stubbed there
    explicitly per-test instead of globally here).
    """
    from api.v1.services.embedding_service import EMBEDDING_SIZE
    from api.v1.services.llm_service import NextQuestion

    fake_qdrant = FakeQdrantClient()

    async def _fake_embed_document_chunks(chunks: list[str]) -> list[list[float]]:
        return [[0.0] * EMBEDDING_SIZE for _ in chunks]

    async def _fake_embed_query(query_text: str) -> list[float]:
        return [0.0] * EMBEDDING_SIZE

    def _fake_upload_to_cloudinary(content: bytes, filename: str) -> str:
        return f"https://res.cloudinary.com/test-cloud/raw/upload/{filename}"

    async def _fake_generate_with_gemini(persona, scenario, topic, messages, client, document_context=None):
        return NextQuestion(
            question_text=f"[stubbed question for {persona.name}]",
            is_followup=len(messages) > 1,
            targets_weakness=None,
        )

    monkeypatch.setattr("api.v1.services.document_service.get_qdrant_client", lambda: fake_qdrant)
    monkeypatch.setattr("api.v1.services.document_service.embed_document_chunks", _fake_embed_document_chunks)
    monkeypatch.setattr("api.v1.services.document_service.embed_query", _fake_embed_query)
    monkeypatch.setattr("api.v1.services.document_service.upload_to_cloudinary", _fake_upload_to_cloudinary)
    monkeypatch.setattr("api.v1.services.llm_service._generate_with_gemini", _fake_generate_with_gemini)


@pytest.fixture
def captured_emails(monkeypatch) -> list[dict]:
    """Stand-in for send_password_reset_email — MAIL_SERVER is unset in the test
    env, so the real function already no-ops without this, but tests that need to
    pull the reset token out of the generated link use this to capture it.

    send_password_reset_email is dispatched via BackgroundTasks from the route
    module (api.v1.routes.auth), which holds its own imported reference to it —
    that's the namespace that must be patched, not api.v1.services.email_service
    where it's defined."""
    sent: list[dict] = []

    async def _fake_send(to_email: str, reset_link: str) -> None:
        sent.append({"to_email": to_email, "reset_link": reset_link})

    monkeypatch.setattr("api.v1.routes.auth.send_password_reset_email", _fake_send)
    return sent
