"""FastAPI auth dependency: resolve the current User from a Bearer JWT.

All data endpoints depend on this and derive the user from the token —
no `?email=` query param (see docs/backend-requirements-from-frontend.md #2).
"""

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.jwt import decode_access_token
from api.db.session import get_db
from api.models.user import User

_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise _UNAUTHORIZED

    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise _UNAUTHORIZED

    subject = claims.get("sub")
    try:
        user_id = uuid.UUID(str(subject))
    except (ValueError, TypeError):
        raise _UNAUTHORIZED

    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise _UNAUTHORIZED

    return user
