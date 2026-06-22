# Backend changes required by the Flutter frontend

**For:** the backend team. **From:** frontend (Flutter) foundation work.
**Date:** 2026-06-22. **Source design:** `docs/superpowers/specs/2026-06-22-frontend-platform-flutter-design.md`.

The frontend is now a **Flutter mobile app** (iOS + Android; web later). This note is the API
**contract + changes** the app needs. Privacy invariants are unchanged and still binding:
**D4** OAuth tokens stay server-side (never on device/in DB beyond Secret Manager), **D5** raw email
bodies never stored, **D19** nothing content-derived ever reaches ads, metadata-first Gmail fetch.

JSON shapes below are the agreed contract — illustrative field names, please keep them or tell us if
they change so we stay in sync.

## Summary

| # | Change | New or Phase 1 | Priority |
|---|--------|----------------|----------|
| 1 | Mobile Google OAuth exchange endpoint | **New** | High (blocks app sign-in) |
| 2 | User model + JWT auth middleware (drop `?email=`) | Phase 1 (now required) | High |
| 3 | Persist extracted items + list API | Phase 1 | High |
| 4 | Device registration for push | **New** | High (blocks reminders) |
| 5 | FCM push sender service | **New** | High |
| 6 | JWT-gate existing sync/extract endpoints | Hardening | Medium |

## 1. Mobile Google OAuth exchange  — NEW

Replaces the web localhost-redirect flow for mobile. The app uses `google_sign_in` to get a
**serverAuthCode** (offline access, scope `gmail.readonly`) and sends it to the backend.

- `POST /api/v1/auth/google/mobile`
- Request: `{ "server_auth_code": "<code>" }`
- Backend: exchange the code for Gmail access+refresh tokens → **store server-side** (D4); find/create
  the `User`; issue an app session JWT.
- Response: `{ "access_token": "<app JWT>", "token_type": "bearer", "expires_in": 900, "user": { "id": "<uuid>", "email": "<addr>" } }`
- GCP note: the mobile app needs **iOS/Android OAuth client IDs** in the same GCP project; the backend
  exchange uses the **web client secret**. (Infra/console setup — see `infra/`.)

## 2. User model + JWT auth middleware  — Phase 1 (now required)

- Add a `User` model (UUID PK, `email` unique, timestamps, `deleted_at` soft-delete).
- JWT issuance + a verification dependency (PyJWT, `SECRET_KEY`/`ALGORITHM` already in env).
- **All data endpoints require `Authorization: Bearer <jwt>` and derive the user from it** — drop the
  `?email=` query param everywhere (this also closes the current `/sync/preview` no-auth issue).

## 3. Persist extracted items + list API  — Phase 1

- Persist extracted `FamilyItem` rows (schema in `backend/api/schemas/family_event.py`:
  `item_type`, `event_title`, `action_required`, `date`, `time`, `location`, `child_name`,
  `event_type`, `source_sender`, `source_email_link`). **Raw email bodies are never stored (D5).**
- `GET /api/v1/items?from=<date>&to=<date>&type=<event|action>` → `{ "items": [FamilyItem, ...] }`
  (JWT-scoped to the user).
- Minimal item update for todos (mark done/dismiss), e.g. `PATCH /api/v1/items/{id}` with
  `{ "status": "done|dismissed" }` — confirm semantics with us; keep MVP-small.

## 4. Device registration for push  — NEW

- `POST /api/v1/devices/register`
- Request: `{ "fcm_token": "<token>", "platform": "ios|android" }`
- Store per user (UUID PK, user_id, token, platform, timestamps, soft-delete); de-dupe by token;
  update on refresh. JWT required.

## 5. FCM push sender service  — NEW

- Backend service sending reminders via **FCM HTTP v1 API** (Firebase service account credentials in
  Secret Manager / env — **not committed**).
- Trigger: when an event/reminder is due — needs a scheduler/worker (aligns with Phase 1 background
  processing). Confirm the scheduling mechanism (cron, task queue, worker).
- Payload: `notification` (title/body) + `data: { "item_id": "<uuid>" }` so the app deep-links to the
  item.
- **iOS requires an APNs auth key uploaded to Firebase** (console step).

## 6. JWT-gate existing sync/extract endpoints  — hardening

- `GET /api/v1/sync/preview`, `/preview-filtered`, `/extract` currently take `?email=` with no auth.
  Secure them with the JWT from #2 and derive the user from the token. Consider `POST /api/v1/sync`
  to trigger a fetch+extract for the authenticated user.

## Infra / config the backend team needs

- Firebase project + **service account** (FCM) and an **APNs key** for iOS push.
- GCP OAuth: **iOS + Android client IDs** (for the app) alongside the existing web client (for the
  backend code exchange).
- New env vars (document in `backend/.env.example`, never commit real values): Firebase service
  account (path or JSON), and any FCM project id. JWT `SECRET_KEY`/`ALGORITHM` already exist.

## Invariants to preserve (firewall / privacy)

- Tokens server-side only (D4); raw bodies never persisted (D5); nothing content-derived to ads
  (D19); metadata-first Gmail fetch (existing known issue — fetch `format="metadata"`, check
  blocklist, then `format="full"` only for senders that pass).

## Open questions for the backend team

- Reminder **scheduling** mechanism (cron / task queue / worker)?
- Item **update** semantics (done / dismiss / snooze) and whether todos and events share one table.
- Pagination needs for `GET /items` (date-range likely enough for MVP).
