"""The background sync job: fetch → blocklist → incremental skip → redact →
extract → persist. One implementation shared by the manual endpoint
(POST /sync backgrounds it) and the hourly auto-sync tick.

Moved from api/routers/sync.py so services never import from routers."""

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.config.settings import settings
from api.models.user import User
from api.services import sync_state
from api.services.ai_extractor import (
    FATAL_EXTRACTION_ERRORS,
    classify_extraction_failure,
    extract_events,
)
from api.services.extraction_budget import has_budget, record_call
from api.services.extraction_gate import has_extractable_signal
from api.services.google_token import ReauthRequired
from api.services.mail_reader import (
    fetch_message_bodies,
    fetch_metadata,
    list_recent_ids,
)
from api.services.items import (
    existing_message_ids,
    mark_message_synced,
    persist_items,
    record_message_failure,
)
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

            provider = user.provider
            # 1. Ids only (cheap). The scan window is wide: capping it at the
            #    per-run size meant anything older than the newest N was never
            #    listed again once those synced — silently unextracted forever,
            #    worst on a new user's 30-day backlog.
            all_ids = await asyncio.to_thread(list_recent_ids, user_email, provider)
            # 2. Dedup on ids BEFORE fetching any headers, so a quiet inbox
            #    costs one list call instead of re-reading the whole window.
            already = await existing_message_ids(db, user_id, all_ids)
            unsynced = [mid for mid in all_ids if mid not in already]
            # 3. Bound the run. Oldest-first so a backlog drains in arrival
            #    order and can never starve behind newer mail; the remainder
            #    stays unmarked and is picked up by the next sync.
            batch_ids = list(reversed(unsynced))[: settings.sync_max_messages_per_run]
            backlog = len(unsynced) - len(batch_ids)

            metadata = await asyncio.to_thread(
                fetch_metadata, user_email, batch_ids, provider
            )
            new_passed, blocked = await _classify(metadata, db)

            bodies = await asyncio.to_thread(
                fetch_message_bodies,
                user_email,
                [m["message_id"] for m, _ in new_passed],
                provider,
            )

            sync_state.progress(
                user_id,
                messages_scanned=len(metadata),
                to_process=len(new_passed),
                processed=0,
                items_created=0,
            )

            items_created = 0
            gate_skipped = 0
            # How many of new_passed we actually got through. Before the budget
            # / circuit-breaker breaks existed this was always len(new_passed);
            # now the loop can end early, and reporting the full count would
            # tell the client "done, all processed" when most were never tried.
            processed = 0
            # Cost telemetry (counts only — audit-safe). Extraction spend was
            # invisible before this; these totals are the per-sync baseline.
            calls = 0
            input_tokens = 0
            output_tokens = 0
            give_ups = 0
            consecutive_failures = 0
            budget_exhausted = False
            for _i, (msg, _status) in enumerate(new_passed):
                # Per-message isolation: a redaction/extraction failure (e.g.
                # a transient Claude API error) skips THIS message and keeps
                # the sync alive. No items row is written for it, so the
                # incremental skip won't hide it — the next sync retries it.
                # (2026-07-15: an invalid tool schema 400'd every extraction
                # and each sync died on its first message.)
                try:
                    body = bodies.get(msg["message_id"], "")
                    # Gate (D36): no temporal token AND no family/action
                    # keyword → the email cannot yield an item. Skip Presidio
                    # + Claude entirely, but still mark it synced (the verdict
                    # is deterministic — re-checking next sync buys nothing).
                    if not has_extractable_signal(msg["subject"], body):
                        gate_skipped += 1
                        await mark_message_synced(db, user_id, msg["message_id"])
                        # Gated messages ARE processed (deliberately, cheaply) —
                        # keep the counter in step or this `continue` would make
                        # the final tally undercount them.
                        processed = _i + 1
                        sync_state.progress(
                            user_id,
                            messages_scanned=len(metadata),
                            to_process=len(new_passed),
                            processed=processed,
                            items_created=items_created,
                        )
                        continue
                    # Hard daily ceiling per user — the backstop against a
                    # runaway we haven't imagined yet. Checked before the
                    # spend, so it caps mid-run rather than after the fact.
                    if not await has_budget(db, user_id):
                        budget_exhausted = True
                        _log.warning(
                            "sync: daily extraction budget exhausted for user %s "
                            "(%d calls); deferring the rest to tomorrow",
                            user_id,
                            settings.extraction_daily_call_budget,
                        )
                        break
                    # Presidio is CPU-bound spaCy analysis — off the loop, or
                    # every concurrent request stalls for the whole sync.
                    redaction = await asyncio.to_thread(redact_pii, body)
                    extraction, usage = await asyncio.to_thread(
                        extract_events,
                        redaction.redacted_text,
                        msg["subject"],
                        msg["sender"],
                        msg["message_id"],
                        msg["date"],
                        provider=provider,
                    )
                    calls += 1
                    input_tokens += usage.input_tokens
                    output_tokens += usage.output_tokens
                    await record_call(
                        db, user_id, usage.input_tokens, usage.output_tokens
                    )
                    saved = await persist_items(db, user, msg["message_id"], extraction.events)
                    items_created += len(saved)
                    # Mark processed AFTER a successful extraction — even when it
                    # yielded zero events — so this message is never re-sent to
                    # Claude. A failed extraction throws before here (see the
                    # handler: it records a bounded failure instead).
                    await mark_message_synced(db, user_id, msg["message_id"])
                    consecutive_failures = 0
                except FATAL_EXTRACTION_ERRORS:
                    # Account-level, not message-level (bad/blocked API key).
                    # Retrying every message would burn the whole batch into a
                    # wall, so fail the run and let the outer handler report it.
                    raise
                except Exception as exc:
                    kind = classify_extraction_failure(exc)
                    # Types only — never message content (audit log rule).
                    _log.warning(
                        "sync: message failed for user %s (%s, %s)",
                        user_id,
                        type(exc).__name__,
                        kind,
                    )
                    # A failed flush/commit leaves the session needing a
                    # rollback; without it every later message would fail too.
                    await db.rollback()
                    # Bound the retry: without a counter a permanently-failing
                    # message was re-sent to Claude every hour for up to 30
                    # days. Accounting must never kill the loop, hence its own
                    # try/except.
                    try:
                        attempts = await record_message_failure(
                            db, user_id, msg["message_id"], kind
                        )
                        if attempts >= settings.extraction_max_attempts:
                            give_ups += 1
                            _log.warning(
                                "sync: giving up on a message for user %s "
                                "after %d attempts (%s)",
                                user_id,
                                attempts,
                                kind,
                            )
                    except Exception as rec_exc:
                        _log.warning(
                            "sync: could not record failure for user %s (%s)",
                            user_id,
                            type(rec_exc).__name__,
                        )
                        await db.rollback()
                    # rollback() expires loaded instances — re-fetch the user
                    # so later iterations don't lazy-refresh in async context
                    # (MissingGreenlet, the reminder-engine Critical's twin).
                    user = await db.get(User, user_id)
                    if user is None:
                        break
                    if kind == "transient":
                        consecutive_failures += 1
                        if consecutive_failures >= settings.extraction_failure_breaker:
                            # A provider outage would otherwise cost a full
                            # batch of failed calls per user, every tick.
                            _log.warning(
                                "sync: aborting run for user %s after %d "
                                "consecutive transient failures",
                                user_id,
                                consecutive_failures,
                            )
                            break
                    else:
                        consecutive_failures = 0
                processed = _i + 1
                sync_state.progress(
                    user_id,
                    messages_scanned=len(metadata),
                    to_process=len(new_passed),
                    processed=processed,
                    items_created=items_created,
                )

            # Per-sync cost summary — counts + the model id only (audit rule:
            # token COUNTS are integers, never token-bearing text). `model` is
            # deliberately included: it makes an accidental EXTRACTION_MODEL
            # flip to a pricier tier attributable from one grep.
            _log.info(
                "sync: user=%s model=%s calls=%d gate_skipped=%d to_process=%d "
                "in_tok=%d out_tok=%d items=%d give_ups=%d budget_exhausted=%s "
                "backlog=%d",
                user_id,
                settings.extraction_model,
                calls,
                gate_skipped,
                len(new_passed),
                input_tokens,
                output_tokens,
                items_created,
                give_ups,
                budget_exhausted,
                backlog,
            )
            if backlog:
                # Visible, not silent: the remainder is queued for the next
                # sync rather than dropped (the pre-fix behaviour).
                _log.info(
                    "sync: %d message(s) queued for the next run for user %s",
                    backlog,
                    user_id,
                )
            sync_state.finish(
                user_id,
                messages_scanned=len(metadata),
                blocked=len(blocked),
                # Actual, not len(new_passed) — a budget/breaker abort leaves
                # the remainder untried and the client must not be told
                # otherwise (they are retried next sync).
                processed=processed,
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
