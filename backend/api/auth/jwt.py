"""App-session JWT issue/verify helpers.

The app holds only this short-lived session JWT (D23); Gmail OAuth tokens
stay server-side (D4). Signed with SECRET_KEY/ALGORITHM from settings.
"""

from datetime import datetime, timedelta, timezone

import jwt

from api.config.settings import settings


def create_access_token(
    subject: str,
    email: str,
    expires_minutes: int | None = None,
) -> str:
    """Issue a signed app-session JWT. `subject` is the user's UUID (str)."""
    minutes = settings.access_token_expire_minutes if expires_minutes is None else expires_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict:
    """Verify signature + expiry and return the claims.

    Raises jwt.ExpiredSignatureError / jwt.InvalidTokenError on failure.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
