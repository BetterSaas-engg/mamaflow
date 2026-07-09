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
   - **Android app** — package `com.bettersaas.mamaflow.mamaflow` → download **`google-services.json`**. The SHA-1 field is **optional — leave it blank**; SHA-1 is only needed for Firebase Auth / Dynamic Links, and we use neither (FCM push does not use it). Our SHA-1, if ever needed later, is `8B:E8:14:1C:8C:E8:73:1F:EB:2D:52:1A:8B:EF:4A:67:7C:D1:B8:B9`.
3. **iOS push** — upload an **APNs auth key** (`.p8`) to the Firebase project's Cloud Messaging settings (needed for iOS delivery).
4. **Backend service account** — Firebase console → Project settings → Service accounts → **Generate new private key** → the JSON. On Railway, set:
   - `FIREBASE_CREDENTIALS_JSON` = the full JSON (one line). This flips the engine on.
   - optionally `REMINDER_TZ` (default `America/Toronto`) and `REMINDER_HOUR` (default `18`).
   Then apply the migration: `cd backend && python -m alembic upgrade head` (the venv python, against Railway).
   > Credential handling (D4): this JSON is env-only — never commit it, never put it in the DB.

## Frontend Firebase wiring — DONE (2026-07-09)

The client wiring is built, tested (54 frontend tests pass), and **emulator-verified**: the app
launches without crashing and logs `FirebaseApp initialization successful`. Security-audited PASS
(only the FCM token + platform leave the device; push is structurally isolated from the ad SDK).

What was added:
- `com.google.gms.google-services` Gradle plugin (`android/settings.gradle.kts` + `app/build.gradle.kts`);
  Firebase pods on iOS (already integrated via `pod install`).
- `Firebase.initializeApp()` in `main.dart` (best-effort — a missing/misconfigured project never
  blocks the app).
- `lib/push/push_service.dart` — requests notification permission, fetches the FCM token, registers
  it via the existing `DeviceRegistrar` (`POST /api/v1/devices/register`), and re-registers on token
  refresh. Triggered from `HomeShell.initState` (i.e. only once signed in). Every step is best-effort.

### The config files are gitignored — must be placed on each build machine

`.gitignore` excludes `frontend/android/app/google-services.json` and
`frontend/ios/Runner/GoogleService-Info.plist` (an existing project decision — client config is not
committed). They are placed on this machine, so local builds work, but **a fresh clone or CI will
not build the app until both files are re-added** to those exact paths.

### One remaining iOS-only manual step (Xcode)

The iOS project (`objectVersion 54`) does not auto-include files. `GoogleService-Info.plist` is on
disk at `ios/Runner/GoogleService-Info.plist` but must be **dragged into the Runner target in Xcode**
(check "Copy items if needed" + the Runner target) so it ships in the app bundle. Not needed for the
Android build; do it before the first iOS/TestFlight build. (Android was fully verified; iOS delivery
also needs the APNs key from step 3 and the Apple Developer account.)

### Build defines (testers / device runs)

Both platforms need the backend URL and iOS OAuth client id at build time:
`--dart-define=API_BASE_URL=https://<railway-url> --dart-define=GOOGLE_IOS_CLIENT_ID=<ios client id>`

## Known limitation (MVP)

Reminders fire at `REMINDER_HOUR` in a **single fixed timezone** (`REMINDER_TZ`). Per-device
timezones (so a user in another region gets "evening before" in *their* local time) is a documented
follow-up — it needs the app to send its IANA timezone at registration (a schema + app change).
