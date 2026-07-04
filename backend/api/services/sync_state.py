"""Per-user sync status registry (in-process, single instance — same scope as
the memory token store). Written by the background sync task, read by
GET /api/v1/sync/status."""

import uuid
from dataclasses import dataclass


@dataclass
class SyncState:
    status: str = "idle"  # idle | running | done | failed
    messages_scanned: int | None = None
    blocked: int | None = None
    processed: int | None = None
    items_created: int | None = None
    error: str | None = None


_states: dict[uuid.UUID, SyncState] = {}


def get_state(user_id: uuid.UUID) -> SyncState:
    return _states.get(user_id, SyncState())


def try_start(user_id: uuid.UUID) -> bool:
    """Mark a sync running; False if one is already in flight for this user."""
    current = _states.get(user_id)
    if current is not None and current.status == "running":
        return False
    _states[user_id] = SyncState(status="running")
    return True


def finish(
    user_id: uuid.UUID,
    messages_scanned: int,
    blocked: int,
    processed: int,
    items_created: int,
) -> None:
    _states[user_id] = SyncState(
        status="done",
        messages_scanned=messages_scanned,
        blocked=blocked,
        processed=processed,
        items_created=items_created,
    )


def fail(user_id: uuid.UUID, error: str) -> None:
    """`error` must be a sanitized, user-safe message — never exception text."""
    _states[user_id] = SyncState(status="failed", error=error)
