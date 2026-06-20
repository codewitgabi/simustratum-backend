from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.response import success_response
from api.v1.dependencies.auth import get_current_access_token, get_current_user
from api.v1.models.user import User
from api.v1.schemas.auth import (
    ChangePasswordRequest,
    GoogleAuthRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    UpdateUserDetailRequest,
)
from api.v1.services import auth as auth_service

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await auth_service.register(body.full_name, body.email, body.password, db)
    return success_response(
        message="Registration successful",
        status_code=status.HTTP_201_CREATED,
        data=result,
    )


@auth_router.post("/login", status_code=status.HTTP_200_OK)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await auth_service.login(body.email, body.password, db)
    return success_response(message="Login successful", data=result)


@auth_router.post("/google", status_code=status.HTTP_200_OK)
async def google_auth(
    body: GoogleAuthRequest, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    result = await auth_service.google_auth(body.id_token, db)
    return success_response(message="Login successful", data=result)


@auth_router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_tokens(
    body: RefreshTokenRequest, db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    result = await auth_service.refresh_tokens(body.refresh_token, db)
    return success_response(message="Tokens refreshed successfully", data=result)


@auth_router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    access_token: str = Depends(get_current_access_token),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await auth_service.logout(access_token, db)
    return success_response(message="Logout successful")


@auth_router.patch("/me", status_code=status.HTTP_200_OK)
async def update_user_detail(
    body: UpdateUserDetailRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    result = await auth_service.update_user_detail(user, body.full_name, db)
    return success_response(message="User details updated successfully", data=result)


@auth_router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await auth_service.change_password(user, body.current_password, body.new_password, db)
    return success_response(message="Password changed successfully")
