from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from api.v1.utils.config import config


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def create_access_token(data: dict[str, Any]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=config.JWT_ACCESS_EXPIRE_MINUTES)
    return _encode({**data, "exp": expire, "type": "access"})


def create_refresh_token(data: dict[str, Any]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=config.JWT_REFRESH_EXPIRE_DAYS)
    return _encode({**data, "exp": expire, "type": "refresh"})


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
