from google.genai import types as genai_types

from api.v1.services.gemini_client import get_gemini_client

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_SIZE = 768


async def embed_document_chunks(chunks: list[str]) -> list[list[float]]:
    """Embeds document chunks for storage. Use embed_query for search-time embedding —
    Gemini's embedding model is asymmetric and expects a different task_type for each."""
    response = await get_gemini_client().aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=chunks,
        config=genai_types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=EMBEDDING_SIZE,
        ),
    )
    return [embedding.values for embedding in response.embeddings]


async def embed_query(query_text: str) -> list[float]:
    response = await get_gemini_client().aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[query_text],
        config=genai_types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_SIZE,
        ),
    )
    return response.embeddings[0].values
