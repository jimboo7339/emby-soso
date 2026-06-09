from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)

JWT_ALGORITHM = "HS256"


def verify_credentials(username: str, password: str) -> bool:
    if not settings.auth_enabled:
        return True
    user_ok = secrets.compare_digest(username, settings.auth_username)
    pass_ok = secrets.compare_digest(password, settings.auth_password)
    return user_ok and pass_ok


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.auth_token_expire_hours)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, settings.auth_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        return str(username) if username else None
    except jwt.PyJWTError:
        return None


def extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials
    cookie_token = request.cookies.get(settings.auth_cookie_name)
    return cookie_token or None


def require_auth(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    if not settings.auth_enabled:
        return "anonymous"

    token = extract_token(request, credentials)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="未登录，请先登录")

    username = decode_access_token(token)
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
    return username


CurrentUser = Annotated[str, Depends(require_auth)]
