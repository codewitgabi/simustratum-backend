from fastapi import APIRouter

from api.v1.routes.auth import auth_router
from api.v1.routes.session import session_router
from api.v1.routes.session_stream import stream_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth_router)
v1_router.include_router(session_router)
v1_router.include_router(stream_router)
