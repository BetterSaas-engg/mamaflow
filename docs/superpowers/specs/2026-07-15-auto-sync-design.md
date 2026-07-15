# Auto-sync — periodic background Gmail sync (design)

**Date:** 2026-07-15 · **Status:** approved (PM, this date)

## Goal

Items and the evening digest stay fresh without the user opening the app: the backend syncs each
user's inbox **hourly**, so email arrives → calendar updates → 6 PM digest reflects it, zero taps.
Today items only appear on a manual "Sync inbox", which makes the reminder digest only as fresh
as the user's last visit.

## Decision summary

- **Cadence:** hourly, at **minute :30** (PM chose hourly; the offset keeps it clear of the
  reminder tick at :00, so the 18:00 digest always reads data ≤30 min old and the jobs never
  contend).
- **Mechanism:** a second job on the existing APScheduler instance (the reminder engine's
  pattern) — no new infrastructure. A task queue (Celery/ARQ) is premature at single-instance
  scale; piggybacking sync onto `reminder_tick` couples unrelated concerns. Both rejected.
- **One sync implementation:** auto-sync calls the same `_run_sync_job` + `sync_state.try_start`
  the manual endpoint uses — auto and manual can never double-run; the manual cooldown carries
  over.

## Components

### 1. `api/services/auto_sync.py` (new)

`async def auto_sync_tick(session_factory) -> None`:

1. One query: candidate user ids/emails = `users` where `deleted_at IS NULL`.
2. Per user, **sequentially**, each wrapped in try/except (one user's failure never stops the
   pass; log `type(exc).__name__` only):
   - `await asyncio.to_thread(get_token, email)` — the Secret Manager backend does blocking
     network I/O, so the lookup runs off the event loop. **No token → skip** (debug log, types
     only). Normal for users who haven't signed in since the last restart, until A1 (Secret
     Manager) is flipped on.
   - `sync_state.try_start(user_id, settings.sync_cooldown_seconds)` — on `already_running` or
     `cooldown`, skip. On `started`, `await _run_sync_job(user_id, email, session_factory)`.

Token-holder enumeration deliberately goes users-table-first (Secret Manager secret ids are
hashed emails by design — the store cannot list token holders globally).

### 2. Scheduler wiring (`api/services/reminder_scheduler.py`)

Today the scheduler only starts when Firebase is configured — correct for reminders, wrong for
auto-sync. Change `start_scheduler(...)`:

- Register the **reminder job** (CronTrigger `minute=0`) iff `push_sender.is_configured()`.
- Register the **auto-sync job** (CronTrigger `minute=30`) iff `settings.auto_sync_enabled`.
- Start the scheduler iff at least one job registered; `stop_scheduler()` unchanged.

### 3. Settings

`auto_sync_enabled: bool = True` — kill switch. Bool parsing is tolerant by pydantic default; an
unparseable value must fall back to `True` with a warning (the 2026-07-15 REMINDER_HOUR outage
rule: a cosmetic knob never takes the API down). Documented in `.env.example`.

## Failure semantics

- Per-user isolation, same as `reminder_tick` and the per-message sync loop.
- Expired-but-refreshable Gmail token: the Gmail reader already refreshes; sync proceeds.
- Revoked grant: that user's sync fails quietly and retries next hour; they stay stale until
  re-sign-in (their app JWT still works; a manual sync surfaces the failure in the UI).
- `sync_state` records per-user outcomes exactly as manual syncs do, so `GET /sync/status` and
  the app's progress card work unchanged.

## Cost

Per user per hour: one Gmail metadata scan (~1–3 API calls). Claude cost is cadence-independent
— the incremental skip (`existing_message_ids`) means only never-seen messages are extracted.

## Testing (mirrors `test_reminder_scheduler.py`; Gmail/Claude/scheduler mocked)

- Skips deleted users and token-less users; syncs token-holders.
- Respects `try_start` (already_running / cooldown → no `_run_sync_job` call).
- One user's exception doesn't stop later users (2-user regression, the Task-4 pattern).
- Kill switch: `auto_sync_enabled=False` → job not registered; Firebase-unconfigured +
  auto-sync-enabled → scheduler still starts with only the sync job (and vice versa).
- Minute offsets asserted (`:0` reminders, `:30` auto-sync).

## Out of scope (YAGNI)

Per-user cadence preferences; "new items found" push notifications (the digest is the
notification); parallel sync workers; queue infrastructure; multi-instance coordination (Railway
runs one instance — same assumption as the token cache, flagged in HANDOFF).

## Dependency note

Ships and works immediately for any user with a live in-memory token; becomes universal once A1
(`TOKEN_STORE_BACKEND=secret-manager`) is activated — no code change needed here.
