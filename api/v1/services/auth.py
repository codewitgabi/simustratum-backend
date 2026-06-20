import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.models.password_reset_token import PasswordResetToken
from api.v1.models.token_blacklist import TokenBlacklist
from api.v1.models.user import AuthProvider, User
from api.v1.schemas.auth import TokenResponse, UserResponse
from api.v1.utils.config import config
from api.v1.utils.jwt_tokens import create_access_token, create_refresh_token, decode_token
from api.v1.utils.password_hash import hash_password, verify_password

_GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _build_tokens(user: User) -> dict[str, Any]:
    payload = {"sub": str(user.id), "email": user.email}
    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
    ).model_dump()


def _build_response(user: User) -> dict[str, Any]:
    return {
        "user": UserResponse.model_validate(user).model_dump(),
        "tokens": _build_tokens(user),
    }


async def register(full_name: str, email: str, password: str, db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account could not be created with the provided details",
        )

    user = User(
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        auth_provider=AuthProvider.EMAIL,
        is_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _build_response(user)


async def login(email: str, password: str, db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or user.auth_provider != AuthProvider.EMAIL or user.password_hash is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return _build_response(user)


async def refresh_tokens(refresh_token: str, db: AsyncSession) -> dict[str, Any]:
    try:
        payload = decode_token(refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id: str = payload.get("sub", "")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    return _build_tokens(user)


async def _verify_google_id_token(id_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        response = await client.get(_GOOGLE_TOKENINFO_URL, params={"id_token": id_token})

    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

    payload = response.json()

    if config.GOOGLE_CLIENT_ID and payload.get("aud") != config.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Google token audience mismatch"
        )

    return payload


async def google_auth(id_token: str, db: AsyncSession) -> dict[str, Any]:
    payload = await _verify_google_id_token(id_token)

    google_id: str = payload.get("sub", "")
    email: str = payload.get("email", "")

    if not google_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token payload"
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            full_name=payload.get("name", ""),
            email=email,
            google_id=google_id,
            auth_provider=AuthProvider.GOOGLE,
            is_verified=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif user.google_id is None:
        user.google_id = google_id
        await db.commit()
        await db.refresh(user)

    return _build_response(user)


async def update_user_detail(user: User, full_name: str, db: AsyncSession) -> dict[str, Any]:
    user.full_name = full_name
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user).model_dump()


async def change_password(
    user: User, current_password: str, new_password: str, db: AsyncSession
) -> None:
    if user.auth_provider != AuthProvider.EMAIL or user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account has no password to change (signed in via Google)",
        )

    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    user.password_hash = hash_password(new_password)
    await db.commit()


async def request_password_reset(
    email: str, client_origin: str, db: AsyncSession
) -> tuple[str, str] | None:
    """
    Returns (recipient_email, reset_link) if a reset email should be sent, or
    None otherwise — caller is responsible for actually sending it (as a
    background task, so this endpoint's response doesn't wait on mail server
    latency). Always returns silently (None) for an unknown email or a
    Google-only account, rather than raising, so this endpoint can't be used to
    enumerate registered emails.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or user.auth_provider != AuthProvider.EMAIL:
        return None

    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_reset_token(raw_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=config.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
    )
    await db.commit()

    reset_link = f"{client_origin}/reset-password?token={raw_token}"
    return user.email, reset_link


async def reset_password(token: str, new_password: str, db: AsyncSession) -> None:
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_reset_token(token))
    )
    record = result.scalar_one_or_none()

    if (
        record is None
        or record.used_at is not None
        or record.expires_at < datetime.now(timezone.utc)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link")

    user_result = await db.execute(select(User).where(User.id == record.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link")

    user.password_hash = hash_password(new_password)
    record.used_at = datetime.now(timezone.utc)
    await db.commit()


def _blacklist_token(token: str, db_session: AsyncSession) -> None:
    payload = decode_token(token)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db_session.add(TokenBlacklist(token_hash=token_hash, expires_at=expires_at))


async def logout(access_token: str, db: AsyncSession) -> None:
    try:
        _blacklist_token(access_token, db)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    await db.commit()
