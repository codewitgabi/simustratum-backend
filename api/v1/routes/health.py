from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.response import success_response

health_router = APIRouter(prefix="/health", tags=["Health"])


@health_router.get("/db")
async def database_health(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT version()"))
    version = result.scalar()
    return success_response(message="Database connection healthy", data={"database": version})
