"""Sync API schemas. The Phase-0 preview/extract response schemas were removed
with their debug GET endpoints (2026-07-10 audit) — extraction results now
reach the client only as persisted items via GET /items."""

from pydantic import BaseModel


class SyncStartResponse(BaseModel):
    status: str  # "started" | "already_running"


class SyncStatusResponse(BaseModel):
    status: str  # "idle" | "running" | "done" | "failed"
    messages_scanned: int | None = None
    blocked: int | None = None
    processed: int | None = None
    to_process: int | None = None
    items_created: int | None = None
    error: str | None = None
