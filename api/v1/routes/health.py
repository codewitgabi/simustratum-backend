from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.response import success_response
from api.v1.services.qdrant_client import get_qdrant_client
from api.v1.utils.config import config

health_router = APIRouter(prefix="/health", tags=["Health"])


@health_router.get("/db")
async def database_health(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT version()"))
    version = result.scalar()
    return success_response(message="Database connection healthy", data={"database": version})


@health_router.get("/qdrant")
async def qdrant_health():
    try:
        collections = await get_qdrant_client().get_collections()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Qdrant is unreachable: {exc}",
        )

    return success_response(
        message="Qdrant connection healthy",
        data={
            "url": config.QDRANT_URL,
            "collection": config.QDRANT_COLLECTION,
            "collections": [c.name for c in collections.collections],
        },
    )
