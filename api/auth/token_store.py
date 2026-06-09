# Phase 0: in-memory token storage
# Phase 1+ moves this to Secret Manager references
_tokens: dict[str, dict] = {}


def store_token(user_email: str, credentials: dict) -> None:
    _tokens[user_email] = credentials


def get_token(user_email: str) -> dict | None:
    return _tokens.get(user_email)


def list_users() -> list[str]:
    return list(_tokens.keys())
