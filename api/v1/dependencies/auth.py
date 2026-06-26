import hashlib

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.v1.models.token_blacklist import TokenBlacklist
from api.v1.models.user import User
from api.v1.utils.jwt_tokens import decode_token
from api.v1.utils.logger import get_logger

logger = get_logger("auth.dependency")

_bearer = HTTPBearer()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _validate_access_token(token: str, db: AsyncSession) -> dict:
    try:
        payload = decode_token(token)
    except Exception as exc:
        logger.warning("Access token decode failed", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    token_hash = hash_token(token)
    result = await db.execute(
        select(TokenBlacklist).where(TokenBlacklist.token_hash == token_hash)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    return payload


async def get_current_access_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> str:
    token = credentials.credentials
    await _validate_access_token(token, db)
    return token


async def _load_user(user_id: str | None, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


async def get_current_user(
    access_token: str = Depends(get_current_access_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(access_token)
    return await _load_user(payload.get("sub"), db)


async def get_current_user_ws(token: str, db: AsyncSession) -> User | None:
    """
    WebSocket variant: no HTTPException machinery (there's no HTTP response to
    attach it to). Returns None on any auth failure so the caller can close the
    socket with a WS-appropriate code instead.
    """
    try:
        payload = await _validate_access_token(token, db)
        return await _load_user(payload.get("sub"), db)
    except HTTPException:
        return None
