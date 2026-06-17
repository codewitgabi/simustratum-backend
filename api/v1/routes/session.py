from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.response import success_response
from api.v1.dependencies.auth import get_current_user
from api.v1.models.user import User
from api.v1.schemas.session import CreateSessionRequest, SessionListItem, SessionResponse
from api.v1.services import session as session_service

session_router = APIRouter(prefix="/sessions", tags=["Sessions"])


@session_router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    session = await session_service.create_session(user.id, body, db)
    return success_response(
        message="Session created successfully",
        status_code=status.HTTP_201_CREATED,
        data=SessionResponse.model_validate(session).model_dump(),
    )


@session_router.get("", status_code=status.HTTP_200_OK)
async def list_sessions(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    sessions, total = await session_service.list_sessions(user.id, page, limit, db)
    items = [
        SessionListItem(
            id=s.id,
            title=s.topic,
            scenario=s.scenario,
            score=0,
            created_at=s.created_at,
        ).model_dump()
        for s in sessions
    ]
    return success_response(
        message="Sessions retrieved successfully",
        data={
            "items": items,
            "meta": {"total": total, "page": page, "limit": limit},
        },
    )
