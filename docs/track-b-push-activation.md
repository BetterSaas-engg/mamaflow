# Track B — Push reminders: activation checklist

The **reminder engine** is built and tested but ships **dark**: with `FIREBASE_CREDENTIALS_JSON`
unset, the sender no-ops and the scheduler never starts, so the app runs exactly as today. Turning
it on is the console + config work below (no code change for the backend engine itself).

## What's already built (backend, inert until step 4)

- `POST /api/v1/devices/register` — the app registers its FCM token (D27).
- `api/services/push_sender.py` — FCM sender via `firebase-admin`; prunes dead tokens.
- `api/services/reminders.py` + `reminder_scheduler.py` — selects tomorrow's open events per user, formats a digest, and an hourly APScheduler job sends the **evening-before digest** at `REMINDER_HOUR` in `REMINDER_TZ`, with per-user daily dedup (`users.last_reminder_date`).
- Migration `d4e3f2a1b0c9` adds `users.last_reminder_date` — **run it** (see step 4).

## Your steps (console + config)

1. **Create a Firebase project** (Firebase console) — you can attach it to the existing GCP project or make a new one.
2. **Register the apps** in that Firebase project:
   - **iOS app** — bundle id matching the Xcode target → download **`GoogleService-Info.plist`**.
   - **Android app** — package `com.bettersaas.mamaflow.mamaflow`, SHA-1 `8B:E8:14:1C:8C:E8:73:1F:EB:2D:52:1A:8B:EF:4A:67:7C:D1:B8:B9` → download **`google-services.json`**.
3. **iOS push** — upload an **APNs auth key** (`.p8`) to the Firebase project's Cloud Messaging settings (needed for iOS delivery).
4. **Backend service account** — Firebase console → Project settings → Service accounts → **Generate new private key** → the JSON. On Railway, set:
   - `FIREBASE_CREDENTIALS_JSON` = the full JSON (one line). This flips the engine on.
   - optionally `REMINDER_TZ` (default `America/Toronto`) and `REMINDER_HOUR` (default `18`).
   Then apply the migration: `cd backend && python -m alembic upgrade head` (the venv python, against Railway).
   > Credential handling (D4): this JSON is env-only — never commit it, never put it in the DB.

## Remaining code follow-up (a separate task, after step 2's config files exist)

The **frontend** Firebase wiring is deliberately *not* built yet, because adding `firebase_core`
init before the config files exist crashes the app on launch (the same class of startup-crash we
already hit with AdMob). Once you have `google-services.json` / `GoogleService-Info.plist`, the
follow-up task will:

- Add the config files (`android/app/google-services.json`, `ios/Runner/GoogleService-Info.plist`)
  and the `com.google.gms.google-services` Gradle plugin (Android) / Firebase pods (iOS).
- Initialize `Firebase.initializeApp()` in `main.dart`.
- Request notification permission, fetch the FCM token (`firebase_messaging`), call the existing
  `DeviceRegistrar.register(fcmToken, platform)`, and handle token refresh + foreground/background
  message display.

Tell me when the config files are ready and I'll build that follow-up.

## Known limitation (MVP)

Reminders fire at `REMINDER_HOUR` in a **single fixed timezone** (`REMINDER_TZ`). Per-device
timezones (so a user in another region gets "evening before" in *their* local time) is a documented
follow-up — it needs the app to send its IANA timezone at registration (a schema + app change).
