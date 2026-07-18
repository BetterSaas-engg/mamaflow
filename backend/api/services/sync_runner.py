"""The background sync job: fetch → blocklist → incremental skip → redact →
extract → persist. One implementation shared by the manual endpoint
(POST /sync backgrounds it) and the hourly auto-sync tick.

Moved from api/routers/sync.py so services never import from routers."""

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.models.user import User
from api.services import sync_state
from api.services.ai_extractor import extract_events
from api.services.google_token import ReauthRequired
from api.services.gmail_reader import fetch_message_bodies, fetch_recent_metadata
from api.services.items import existing_message_ids, persist_items
from api.services.privacy_pipeline import redact_pii
from api.services.sender_blocklist import is_blocked_sender

_log = logging.getLogger(__name__)


def _blocked_entry(msg: dict, result) -> dict:
    return {
        "message_id": msg["message_id"],
        "sender": msg["sender"],
        "subject": msg["subject"],
        "date": msg["date"],
        "reason": result.reason,
        "category": result.category,
        "list_status": result.list_status,
    }


async def _classify(metadata: list[dict], db: AsyncSession):
    """Split scanned metadata into (passed, blocked) without fetching any body.

    `passed` carries each message dict plus its allowed/unknown list_status.
    """
    passed = []
    blocked = []
    for msg in metadata:
        result = await is_blocked_sender(msg["sender"], db)
        if result.list_status == "blocked":
            blocked.append(_blocked_entry(msg, result))
        else:
            passed.append((msg, result.list_status))
    return passed, blocked


async def run_sync_job(
    user_id: uuid.UUID,
    user_email: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The background sync: fetch → blocklist → incremental skip → redact →
    extract → persist. Opens its own session (the request's is closed by now).
    Reports progress/outcome via sync_state; errors are sanitized."""
    try:
        async with session_factory() as db:
            user = await db.get(User, user_id)
            if user is None:
                sync_state.fail(user_id, "user not found")
                return

            metadata = await asyncio.to_thread(fetch_recent_metadata, user_email)
            passed, blocked = await _classify(metadata, db)

            # Incremental: drop already-synced messages BEFORE body fetch and
            # extraction — dedup after the Claude call would still spend tokens.
            already = await existing_message_ids(
                db, user_id, [m["message_id"] for m, _ in passed]
            )
            new_passed = [
                (m, s) for m, s in passed if m["message_id"] not in already
            ]

            bodies = await asyncio.to_thread(
                fetch_message_bodies,
                user_email,
                [m["message_id"] for m, _ in new_passed],
            )

            sync_state.progress(
                user_id,
                messages_scanned=len(metadata),
                to_process=len(new_passed),
                processed=0,
                items_created=0,
            )

            items_created = 0
            for _i, (msg, _status) in enumerate(new_passed):
                # Per-message isolation: a redaction/extraction failure (e.g.
                # a transient Claude API error) skips THIS message and keeps
                # the sync alive. No items row is written for it, so the
                # incremental skip won't hide it — the next sync retries it.
                # (2026-07-15: an invalid tool schema 400'd every extraction
                # and each sync died on its first message.)
                try:
                    # Presidio is CPU-bound spaCy analysis — off the loop, or
                    # every concurrent request stalls for the whole sync.
                    redaction = await asyncio.to_thread(
                        redact_pii, bodies.get(msg["message_id"], "")
                    )
                    extraction = await asyncio.to_thread(
                        extract_events,
                        redaction.redacted_text,
                        msg["subject"],
                        msg["sender"],
                        msg["message_id"],
                        msg["date"],
                    )
                    saved = await persist_items(db, user, msg["message_id"], extraction.events)
                    items_created += len(saved)
                except Exception as exc:
                    # Types only — never message content (audit log rule).
                    _log.warning(
                        "sync: skipping one message for user %s (%s)",
                        user_id,
                        type(exc).__name__,
                    )
                    # A failed flush/commit leaves the session needing a
                    # rollback; without it every later message would fail too.
                    await db.rollback()
                    # rollback() expires loaded instances — re-fetch the user
                    # so later iterations don't lazy-refresh in async context
                    # (MissingGreenlet, the reminder-engine Critical's twin).
                    user = await db.get(User, user_id)
                    if user is None:
                        break
                sync_state.progress(
                    user_id,
                    messages_scanned=len(metadata),
                    to_process=len(new_passed),
                    processed=_i + 1,
                    items_created=items_created,
                )

            sync_state.finish(
                user_id,
                messages_scanned=len(metadata),
                blocked=len(blocked),
                processed=len(new_passed),
                items_created=items_created,
            )
    except ReauthRequired:
        # The Gmail token can't be refreshed (revoked/absent). Types-only log
        # (user_id, no email/traceback), and a client message that tells the
        # user what to actually do. Must precede the generic handler, whose
        # _log.exception would attach the full traceback.
        _log.warning("sync: reauth required for user %s", user_id)
        sync_state.fail(user_id, "Please sign in again.")
    except Exception:
        # Full detail to server logs; only a sanitized message to the client.
        _log.exception("sync failed for user %s", user_id)
        sync_state.fail(user_id, "Sync failed. Try again.")
