"""The background sync job: fetch → blocklist → incremental skip → redact →
extract → persist. One implementation shared by the manual endpoint
(POST /sync backgrounds it) and the hourly auto-sync tick.

Moved from api/routers/sync.py so services never import from routers."""

import asyncio
import dataclasses
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
from api.services.mail_connections import list_connections
from api.services.items import (
    existing_message_ids,
    mark_message_synced,
    mark_messages_blocked,
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
    Reports progress/outcome via sync_state; errors are sanitized.

    Runs over EVERY mailbox the user has connected (D44 tiers allow up to 2).
    The per-run message cap is shared across them, not applied per mailbox —
    otherwise a family with four mailboxes would cost four times as much per
    tick, which is exactly the runaway D39 was about. Dedup and the extraction
    budget are already per user, so mail arriving in two mailboxes is extracted
    once.
    """
    try:
        async with session_factory() as db:
            user = await db.get(User, user_id)
            if user is None:
                sync_state.fail(user_id, "user not found")
                return

            mailboxes = await list_connections(db, user_id)
            totals = _Totals()
            reauth_needed = 0
            for mailbox in mailboxes:
                if totals.remaining(settings.sync_max_messages_per_run) <= 0:
                    break
                try:
                    stop = await _sync_one_mailbox(db, user, mailbox, totals)
                except ReauthRequired:
                    # One dead mailbox must not take the others down with it —
                    # the whole point of supporting more than one.
                    reauth_needed += 1
                    _log.warning(
                        "sync: reauth required for a mailbox of user %s (%s)",
                        user_id,
                        mailbox.provider,
                    )
                    continue
                if stop:
                    break

            if mailboxes and reauth_needed == len(mailboxes):
                # Every mailbox is broken: this IS a sign-in problem.
                raise ReauthRequired
            await _report(user_id, totals)
    except ReauthRequired:
        # The mail credential can't be refreshed (revoked/absent). Types-only
        # log (user_id, no email/traceback), and a client message that tells the
        # user what to actually do. Must precede the generic handler, whose
        # _log.exception would attach the full traceback.
        _log.warning("sync: reauth required for user %s", user_id)
        sync_state.fail(user_id, "Please sign in again.")
    except Exception:
        # Full detail to server logs; only a sanitized message to the client.
        _log.exception("sync failed for user %s", user_id)
        sync_state.fail(user_id, "Sync failed. Try again.")


@dataclasses.dataclass
class _Totals:
    """Counters aggregated across a user's mailboxes for one sync run."""

    messages_scanned: int = 0
    blocked: int = 0
    processed: int = 0
    items_created: int = 0
    calls: int = 0
    gate_skipped: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    give_ups: int = 0
    backlog: int = 0
    budget_exhausted: bool = False

    def remaining(self, per_run_cap: int) -> int:
        """Messages this run may still take, shared across mailboxes."""
        return max(0, per_run_cap - self.processed)


async def _report(user_id: uuid.UUID, t: _Totals) -> None:
    # Per-sync cost summary — counts + the model id only (audit rule: token
    # COUNTS are integers, never token-bearing text). `model` is deliberately
    # included: it makes an accidental EXTRACTION_MODEL flip to a pricier tier
    # attributable from one grep.
    _log.info(
        "sync: user=%s model=%s calls=%d gate_skipped=%d to_process=%d "
        "in_tok=%d out_tok=%d items=%d give_ups=%d budget_exhausted=%s "
        "backlog=%d",
        user_id,
        settings.extraction_model,
        t.calls,
        t.gate_skipped,
        t.processed,
        t.input_tokens,
        t.output_tokens,
        t.items_created,
        t.give_ups,
        t.budget_exhausted,
        t.backlog,
    )
    if t.backlog:
        # Visible, not silent: the remainder is queued for the next sync rather
        # than dropped (the pre-fix behaviour).
        _log.info(
            "sync: %d message(s) queued for the next run for user %s",
            t.backlog,
            user_id,
        )
    sync_state.finish(
        user_id,
        messages_scanned=t.messages_scanned,
        blocked=t.blocked,
        # Actual, not len(new_passed) — a budget/breaker abort leaves the
        # remainder untried and the client must not be told otherwise (they
        # are retried next sync).
        processed=t.processed,
        items_created=t.items_created,
    )


async def _sync_one_mailbox(
    db: AsyncSession,
    user: User,
    mailbox,
    totals: _Totals,
) -> bool:
    """Sync a single mailbox. Returns True if the whole run should stop (the
    daily budget or the failure breaker tripped — both are per USER, so there
    is no point continuing into the next mailbox)."""
    user_id = user.id
    user_email = mailbox.email
    provider = mailbox.provider
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
    #    The cap is what's LEFT for this run, not the full per-run number:
    #    applied per mailbox it would multiply cost by the mailbox count.
    batch_ids = list(reversed(unsynced))[
        : totals.remaining(settings.sync_max_messages_per_run)
    ]
    backlog = len(unsynced) - len(batch_ids)

    metadata = await asyncio.to_thread(
        fetch_metadata, user_email, batch_ids, provider
    )
    new_passed, blocked = await _classify(metadata, db)
    scanned = len(metadata)
    # 4. Retire the blocked ids. They are a terminal verdict reached
    #    from headers alone, but leaving them unmarked kept them in the
    #    oldest-first pool forever — enough blocked mail in the window
    #    (easy: the seed blocklist covers high-volume senders) and every
    #    batch was 100% blocked ids while real mail waited behind them.
    await mark_messages_blocked(
        db, user_id, [b["message_id"] for b in blocked]
    )

    bodies = await asyncio.to_thread(
        fetch_message_bodies,
        user_email,
        [m["message_id"] for m, _ in new_passed],
        provider,
    )

    _progress(user_id, totals, scanned, 0, 0)

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
    stop_run = False
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
                _progress(user_id, totals, scanned, processed, items_created)
                continue
            # Hard daily ceiling per user — the backstop against a
            # runaway we haven't imagined yet. Checked before the
            # spend, so it caps mid-run rather than after the fact.
            if not await has_budget(db, user_id):
                budget_exhausted = True
                stop_run = True
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
                    stop_run = True
                    break
            else:
                consecutive_failures = 0
        processed = _i + 1
        _progress(user_id, totals, scanned, processed, items_created)

    totals.messages_scanned += scanned
    totals.blocked += len(blocked)
    totals.processed += processed
    totals.items_created += items_created
    totals.calls += calls
    totals.gate_skipped += gate_skipped
    totals.input_tokens += input_tokens
    totals.output_tokens += output_tokens
    totals.give_ups += give_ups
    totals.backlog += backlog
    totals.budget_exhausted = totals.budget_exhausted or budget_exhausted
    return stop_run


def _progress(
    user_id: uuid.UUID,
    totals: _Totals,
    scanned: int,
    processed: int,
    items_created: int,
) -> None:
    """Report the RUN's aggregate, not just the current mailbox — otherwise the
    counters would visibly reset each time sync moved to the next mailbox."""
    sync_state.progress(
        user_id,
        messages_scanned=totals.messages_scanned + scanned,
        to_process=totals.processed + processed,
        processed=totals.processed + processed,
        items_created=totals.items_created + items_created,
    )
