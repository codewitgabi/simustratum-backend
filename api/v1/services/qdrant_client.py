from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models

from api.v1.services.embedding_service import EMBEDDING_SIZE
from api.v1.utils.config import config
from api.v1.utils.logger import get_logger

logger = get_logger("qdrant_client")

_collection_ready = False

@lru_cache
def get_qdrant_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None, timeout=120)


async def ensure_collection_exists(client: AsyncQdrantClient) -> None:
    """
    Uses the configured collection if it already exists; creates it (with a single
    default vector matching EMBEDDING_SIZE, plus a tenant index on document_id)
    if it doesn't. Cached in-process after the first successful check so this isn't
    a round trip on every embed/retrieve call.
    """
    global _collection_ready
    if _collection_ready:
        return

    if await client.collection_exists(config.QDRANT_COLLECTION):
        _collection_ready = True
        return

    logger.info("Creating Qdrant collection", extra={"collection": config.QDRANT_COLLECTION})
    await client.create_collection(
        collection_name=config.QDRANT_COLLECTION,
        vectors_config=models.VectorParams(size=EMBEDDING_SIZE, distance=models.Distance.COSINE),
    )
    await client.create_payload_index(
        collection_name=config.QDRANT_COLLECTION,
        field_name="document_id",
        field_schema=models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD, is_tenant=True),
    )
    _collection_ready = True


async def connect() -> None:
    """Verifies Qdrant is reachable and the collection is ready, at app startup."""
    client = get_qdrant_client()
    await client.get_collections()
    await ensure_collection_exists(client)
    logger.info("Qdrant connected", extra={"url": config.QDRANT_URL, "collection": config.QDRANT_COLLECTION})


async def disconnect() -> None:
    await get_qdrant_client().close()
    logger.info("Qdrant disconnected")
