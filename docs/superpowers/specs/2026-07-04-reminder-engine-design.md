# Design — Reminder engine (Track B push, backend)

**Date:** 2026-07-04
**Status:** Approved (brainstorming) — pending implementation plan.
**Roadmap:** HANDOFF.md Track B (D22/D26/D27). The push **sender + scheduler**, deferred in D27 until Firebase creds exist. This builds the backend reminder engine now (TDD, inert until configured — the A1 pattern); the Firebase console setup + frontend token wiring are the gated activation follow-up.

## Problem

Mamaflow extracts family events but never reminds anyone. The `Device` model + `POST /devices/register` exist (D27), but there's no push sender and no scheduler — so a "dentist tomorrow at 10am" event just sits in the app until the parent happens to open it. The value of surfacing events is realized only when the app proactively reminds them.

## Goal

Once a day (evening before), send each user a push listing **tomorrow's** events. The engine is fully built + tested now but **inert until a Firebase service account is configured** — flipping it on is a config change, no code change (mirrors A1's Secret-Manager gating).

## Scope

**In (buildable now, backend):**
- Push sender via `firebase-admin` (FCM HTTP v1), inert without creds; prunes dead tokens.
- Reminder selection + digest formatting (pure).
- APScheduler hourly job (D26) in the FastAPI lifespan; sends at the reminder hour; dedup.
- One migration: `users.last_reminder_date`.
- Config: `FIREBASE_CREDENTIALS_JSON`, `REMINDER_TZ`, `REMINDER_HOUR`.

**Out (gated on the user's console work; documented as the activation checklist):**
- Firebase project; iOS + Android app registration → `google-services.json` / `GoogleService-Info.plist`; APNs key; the service-account JSON.
- **Frontend** Firebase wiring (init, notification permission, FCM token fetch/refresh, `DeviceRegistrar` call, foreground/background message handlers). Built **after** the config files exist — adding it now would crash the app on launch (like AdMob did) because `firebase_core` needs the platform config.
- Per-device timezone (see Decisions), per-event "N-hours-before" reminders, new-items-after-sync pushes.

## Architecture

```
APScheduler (hourly, in lifespan)
   └─ reminder_tick(now):  only when hour == REMINDER_HOUR in REMINDER_TZ
        for each user with device(s) AND last_reminder_date != today(TZ):
          items = open dated events where date == tomorrow(TZ)   ── reminders.select
          if items: digest = format(items)                       ── reminders.format
                    push_sender.send(user's tokens, digest)      ── firebase-admin
                    prune dead tokens (soft-delete)
          user.last_reminder_date = today(TZ)                    ── dedup
```

### 1. Push sender — `backend/api/services/push_sender.py`

- `is_configured() -> bool` — true iff `settings.firebase_credentials_json` is non-empty.
- Lazy one-time `firebase_admin.initialize_app(credential.Certificate(json.loads(...)))` on first send (guarded so tests/dev without creds never touch Firebase).
- `async send_digest(tokens: list[str], title: str, body: str) -> list[str]` — sends a multicast message; returns the list of **dead tokens** (FCM error codes `UNREGISTERED` / `INVALID_ARGUMENT` for the token). Blocking `firebase_admin.messaging` calls run off the event loop (`asyncio.to_thread`). If not configured, returns `[]` and sends nothing.
- No message content is ever logged (types/counts only) — the digest text is event titles (user content); it goes only to the user's own device via FCM, never to logs or any third party beyond Google's push transport.

### 2. Reminder selection — `backend/api/services/reminders.py`

- `async users_with_devices(db) -> list[User]` — users having ≥1 non-deleted device.
- `async tomorrow_events(db, user, target_date: str) -> list[Item]` — `Item.user_id == user.id`, `deleted_at IS NULL`, `status == 'open'`, `item_type == 'event'`, `event_date == target_date` (ISO string equality). (Dateless actions and done/dismissed items are excluded.)
- `format_digest(items) -> (title, body)` — pure. Title `"Tomorrow's schedule"`; body joins each event as `"<title> <time?>"`, e.g. `"Charlie's dentist 10:00 AM · Soccer practice 4:00 PM"`. Caps the body length (e.g. first 5 events + "and N more") to keep the push small.
- `device_tokens(db, user) -> list[str]` — the user's non-deleted device FCM tokens.

### 3. Scheduler — `backend/api/services/reminder_scheduler.py` + lifespan wiring

- `async reminder_tick(session_factory, *, now)` — the core, testable **independently of the scheduler**: computes `today`/`tomorrow` in `REMINDER_TZ`; if `now`'s hour (in `REMINDER_TZ`) != `REMINDER_HOUR`, returns immediately (no-op). Otherwise iterates `users_with_devices`; for each user where `last_reminder_date != today` **and** `tomorrow_events` is non-empty, it sends the digest, prunes dead tokens, and sets `last_reminder_date = today` (committed). Dedup semantics: `last_reminder_date` is advanced **only on a send**, so a user with no events tomorrow is simply skipped (not marked) and re-checked at the next day's reminder hour; and the `!= today` guard makes a repeat tick within the same hour (or a restart at ~18:00) a no-op. The hourly cron means each user is evaluated once per day at the reminder hour.
- `start_scheduler(app)` / `stop_scheduler(app)` — create an `AsyncIOScheduler`, add `reminder_tick` as an hourly cron job (uses `get_session_factory` for its own session), start in the FastAPI `lifespan`, shut down on exit. If `not push_sender.is_configured()`, log once and **don't start** the job (fully inert).

### 4. Dedup migration

- Alembic migration adding `users.last_reminder_date: Date | None` (nullable). Applied by the **user** against Railway (Claude can't write the shared DB — memory `railway-migration-permission`).

### 5. Config — `settings.py`

- `firebase_credentials_json: str = ""` — the service-account JSON (a credential; env only, never DB, D4). Empty = engine inert.
- `reminder_tz: str = "America/Toronto"` — IANA tz for "evening before".
- `reminder_hour: int = 18` — local hour to send.

## Data flow / correctness

- Dates: items store `event_date` as ISO `YYYY-MM-DD`. `tomorrow` is computed as the calendar date after today in `REMINDER_TZ`, formatted ISO — string equality matches. (The A0 backfill/normalizer ensures dated items carry ISO dates.)
- Single instance: the scheduler runs in one process (matches C's single-instance token-cache constraint). Not safe to run N replicas without a distributed lock — documented.

## Error handling

- Not configured → sender no-ops, scheduler job not started. The app runs exactly as today.
- `firebase-admin` init failure (bad JSON) → logged sanitized once; sender stays inert; never crashes the app or the request path (the scheduler job catches + logs per-tick).
- Per-user send failure inside a tick is caught + logged (sanitized) so one user's failure doesn't abort the whole tick; `last_reminder_date` is only advanced on success.
- Dead tokens (FCM `UNREGISTERED`/invalid) → soft-delete those device rows (prune). This also mitigates the device-reassignment note in `devices.py` (stale tokens get cleaned).

## Testing (pytest; firebase-admin + scheduler mocked — never live)

- **push_sender:** `is_configured()` reflects the env; when unconfigured, `send_digest` returns `[]` and never calls firebase; when configured (monkeypatched `firebase_admin.messaging.send_each_for_multicast`), it sends and returns the dead tokens parsed from the mocked batch response.
- **reminders:** `tomorrow_events` returns only open, dated, event-type items for the target date scoped to the user (excludes done/dismissed, dateless, other users, wrong date); `format_digest` formats + caps; `device_tokens`/`users_with_devices` scope correctly.
- **reminder_tick:** with a monkeypatched sender, a user with a tomorrow-event + device gets one send and `last_reminder_date` set; a second tick same day sends nothing (dedup); off-hour ticks do nothing; a user with no devices / no tomorrow-events is skipped; a dead token from the send soft-deletes that device.
- **lifespan:** unconfigured → scheduler job not registered (inert); no live scheduler in tests.
- Full suite green; `firewall-guard` green.

## Firewall / privacy invariants

- **D19 (firewall):** the digest (event titles/times) is delivered only to the user's own device via FCM. It is **not** content for ad targeting; nothing here touches the ad layer. No ad surface added.
- **D5:** no raw email body — only already-extracted structured event fields feed the digest.
- **D4:** the Firebase service-account JSON is a credential handled via env, **never** written to the DB; no token value or digest text is logged.
- Security-auditor pass before finishing (touches data persistence — device pruning + `users.last_reminder_date` — and a new outbound credential).

## Decisions taken

- **Trigger = evening-before digest** (one push/day listing tomorrow's events).
- **Timezone = fixed configurable default** (`REMINDER_TZ=America/Toronto`) for MVP; per-device IANA tz is the documented follow-up (schema + app change). Known limitation: mistimed for users in other regions until then.
- **`firebase-admin`** for FCM HTTP v1 (auth + batching + per-token errors).
- **Inert-until-configured** via `FIREBASE_CREDENTIALS_JSON` (A1 pattern) — the engine ships dark and is flipped on by config, no code change.
- **Dedup** via a nullable `users.last_reminder_date` (one user-applied migration).
