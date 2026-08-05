"""Shared test setup.

Since D44 a user's mailboxes live in `mail_connections`, so sync reads from
there rather than from `users.provider`. A user created straight through
`get_or_create_user` has no mailbox and correctly syncs nothing — real users
always get a connection during sign-in — so tests that exercise sync must
create one explicitly.
"""

from api.auth.jwt import create_access_token
from api.services.mail_connections import ensure_connection
from api.services.users import get_or_create_user


async def user_with_mailbox(db, email="parent@example.com", provider="google"):
    """A user with one connected mailbox, plus their session token."""
    user = await get_or_create_user(db, email, provider=provider)
    await ensure_connection(db, user, provider, email)
    return user, create_access_token(subject=str(user.id), email=user.email)
