"""Per-user sync status registry (in-process, single instance — same scope as
the memory token store). Written by the background sync task, read by
GET /api/v1/sync/status."""

import time
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
    # Internal (never serialized to the API): monotonic completion time,
    # used for the per-user cooldown between syncs.
    finished_monotonic: float | None = None


_states: dict[uuid.UUID, SyncState] = {}


def get_state(user_id: uuid.UUID) -> SyncState:
    return _states.get(user_id, SyncState())


def try_start(user_id: uuid.UUID, cooldown_seconds: float = 0) -> tuple[str, float]:
    """Attempt to mark a sync running for this user.

    Returns (outcome, retry_after_seconds):
      ("started", 0)          — sync may proceed
      ("already_running", 0)  — one is in flight
      ("cooldown", n)         — last sync finished < cooldown_seconds ago
    """
    current = _states.get(user_id)
    if current is not None:
        if current.status == "running":
            return "already_running", 0
        if cooldown_seconds and current.finished_monotonic is not None:
            elapsed = time.monotonic() - current.finished_monotonic
            if elapsed < cooldown_seconds:
                return "cooldown", cooldown_seconds - elapsed
    _states[user_id] = SyncState(status="running")
    return "started", 0


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
        finished_monotonic=time.monotonic(),
    )


def fail(user_id: uuid.UUID, error: str) -> None:
    """`error` must be a sanitized, user-safe message — never exception text."""
    _states[user_id] = SyncState(
        status="failed", error=error, finished_monotonic=time.monotonic()
    )
