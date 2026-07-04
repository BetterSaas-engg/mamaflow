# Mamaflow — Developer Handoff (Phase 0 Complete)

**Date:** 2026-06-13
**Status:** Phase 0 complete. End-to-end pipeline verified against a live Gmail inbox.

> **Update 2026-06-22 — AI-assistant setup + repo restructure.** All backend code now lives under
> `backend/` (package still `api`, imports unchanged; run commands from `backend/`). AI-assistant
> scaffolding installed at the repo root: `AGENTS.md` (canonical, cross-tool), `CLAUDE.md`/`GEMINI.md`,
> `.claude/` + `.agents/`, and the deterministic firewall (`scripts/firewall-guard.sh` wired as a
> Claude PostToolUse hook + `.githooks/pre-commit` backstop). Added 4 project skills
> (firewall-privacy-audit, testing, code-maintainability-audit, db-migrations) and `DECISIONS.md`
> (D1–D21; **D9/D20 frontend platform under review** — PWA+Capacitor vs Expo vs Flutter). Memory model:
> docs + discipline (manual) — update this file after each step. Verified in a venv:
> `cd backend && python -m pytest` → **7 passed**. Tracked on branch `chore/ai-assistant-setup`
> (pushed to origin; not merged to main). See `AI-SETUP.md`.

> **Update 2026-06-22 — Frontend platform decided: Flutter.** Mobile-first (iOS + Android), web later;
> push via FCM; mobile Google OAuth (tokens stay server-side). Supersedes D9/D20 (decision-log flip +
> D22/D23 done). Design:
> `docs/superpowers/specs/2026-06-22-frontend-platform-flutter-design.md`. **Backend team:** the
> required API contract + changes are in `docs/backend-requirements-from-frontend.md`. Frontend work
> on branch `feat/frontend-flutter` (pushed). **Phase 0** (D9/D20→Flutter + D22/D23; firewall-guard
> Dart patterns) and **Phase 1** (Flutter app foundation: `frontend/` scaffold + api_client / auth /
> isolated ads / push / app-shell; 7 tests pass; `flutter analyze` clean) are **done**. **Phase 2**
> (on-device Firebase/FCM, Google sign-in, AdMob, wired to the backend endpoints) is pending accounts
> + backend. Plan: `docs/superpowers/plans/2026-06-22-frontend-flutter-foundation.md`.

> **Update 2026-06-23 — Backend Phase 1 (frontend integration) A–D done.** Built the API contract the
> Flutter app needs (`docs/backend-requirements-from-frontend.md`), TDD, on branch
> `feat/backend-mobile-integration`. **44 tests pass.** New env in `backend/.env` (real Railway/Google/
> Anthropic + a generated `SECRET_KEY`; gitignored). Commits: A `88a9317`, B `f6a59ed`, C `9663ab7`,
> D `de9614c`.
> - **A (auth):** `User` model; JWT issue/verify + `get_current_user` Bearer dependency;
>   `POST /api/v1/auth/google/mobile` (serverAuthCode → Gmail tokens server-side D4 → app JWT D23).
> - **B (items):** single `items` table (D24); `persist_items` (idempotent per message);
>   `GET /api/v1/items?from&to&type`, `PATCH /api/v1/items/{id}` {status open/done/dismissed, D25}.
> - **C (hardening):** all sync endpoints JWT-gated, `?email=` dropped; **metadata-first Gmail fetch**
>   (blocked senders' bodies never pulled — fixes the long-standing gap); `POST /api/v1/sync`
>   (fetch→blocklist→redact→extract→persist); blocking I/O moved off the loop via `asyncio.to_thread`.
> - **D (push):** `Device` model + `POST /api/v1/devices/register` (de-dupe by fcm_token). FCM sender +
>   APScheduler reminder job DEFERRED until Firebase service account + APNs key exist (D26/D27).
> - **Migrations:** 3 new (users `105f5ff0fdeb`, items `b2c1d0e9f8a7`, devices `c3d2e1f0a9b8`), verified
>   as valid Postgres DDL offline. **NOT yet applied to the shared Railway DB** — run
>   `cd backend && python -m alembic upgrade head` (Claude was blocked from writing the shared DB).
> - Security-audited (A, B, C, D — no BLOCKs). Test DB = in-memory SQLite (`tests/conftest.py`).
>   Tracked from the C/D audit for the FCM-sender phase: device re-registration reassigns `user_id`
>   by `fcm_token` ("last registration wins" — required for device-switch; residual low-impact hijack
>   risk, inert until pushes are sent — see `services/devices.py` docstring).

> **Update 2026-07-02 — E2E VERIFIED ON A REAL iPHONE.** Full loop working on device: Google
> sign-in → Gmail fetch (metadata-first) → blocklist → Presidio → Claude → Railway Postgres →
> app list (sync idempotent; done/dismiss working). Migrations applied to Railway (head
> `c3d2e1f0a9b8`). Root `README.md` added (setup + run-on-device instructions).
> - **D28 pivot:** mobile sign-in is now direct OAuth2 auth-code + **PKCE** via flutter_web_auth_2
>   (google_sign_in 7.x cannot mint a Gmail-scoped serverAuthCode on iOS — verified in plugin
>   source). Backend `POST /auth/google/mobile` takes `{code, code_verifier}`; redirect_uri derived
>   server-side; new env `GOOGLE_IOS_CLIENT_ID`. PKCE flow security-audited (no BLOCKs; findings
>   fixed in 829bb67).
> - iOS config: deployment target 15.0 (Firebase SPM); Info.plist has GIDClientID + reversed-id URL
>   scheme + GADApplicationIdentifier (Google TEST id — replace before release) + dev-only ATS.
> - ~~Extraction date formats~~ **FIXED** (`1e1bba2`, `a702b09`): prompt forces ISO YYYY-MM-DD
>   (Date header added to the wrap for reference) + deterministic `normalize_item_date` backstop.
>   Audit of the change found + fixed a BLOCK: spoofed Date headers (OverflowError) could 500 a
>   whole sync batch.
> - ~~JWT expiry UX~~ **FIXED** (`f2b0b7c`): 401 → auto sign-out (ApiClient onUnauthorized →
>   SessionController → auth gate shows sign-in).
> - **Known issues (next up):**
>   1. Gmail tokens in-memory — backend restart loses them (re-sign-in required); Secret Manager is
>      the Phase-1 fix.
>   2. Sync is synchronous on the request path (~50 Claude calls worst case) — background processing
>      still pending (Phase 1 list).
>   3. Pre-existing (audit note): `ai_extractor` logs a 200-char raw_text snippet on JSON-parse
>      failure — arguably violates the types-only log rule; clean up with the tool-use/structured-
>      output hardening.
> - Branch `feat/backend-mobile-integration` pushed; **PR #1 open**
>   (https://github.com/BetterSaas-engg/mamaflow/pull/1) — merge pending PM review.

## Roadmap (agreed 2026-07-03)

| Track | What | Gate / status |
|-------|------|---------------|
| A1 | Persistent Gmail tokens — **Secret Manager** (D4 forbids DB storage, even encrypted); in-memory stays the dev default | **Code DONE** (`cbbbe71`+`01a89ce`, audited PASS). **User-side BLOCKED**: the `optimacore.io` org enforces `iam.disableServiceAccountKeyCreation` (Secure-by-Default), so the service-account JSON key can't be created yet. **Plan:** deploy Railway with `TOKEN_STORE_BACKEND=memory` now (re-sign-in after each restart — acceptable in Testing); later an org admin (Sabiran/Akhil with `roles/orgpolicy.policyAdmin`, granted at the ORG level) creates a **project-scoped override** (Mamaflow project → IAM & Admin → Organization Policies → "Disable service account key creation" → Override parent → Enforcement Off), then creates the key (svc acct `mamaflow-backend`, role Secret Manager Admin) and flips the Railway vars (`TOKEN_STORE_BACKEND=secret-manager`, `GCP_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`). No code change needed. Keyless alternative if this drags: host backend in GCP (Cloud Run attaches the svc acct without any key). |
| C | Deploy backend to Railway (Dockerfile, https, prod SECRET_KEY; kills dev ATS/cleartext exceptions). ⚠️ Audit flag: the token store's in-process cache is NOT multi-instance coherent — instance A's token refresh won't invalidate instance B's cache. Single instance only until a TTL/invalidation hook lands. | **DONE 2026-07-03** — live at https://mamaflow-production.up.railway.app (health/routes/auth verified; **full-cloud E2E from iPhone confirmed**: sign-in → sync → items, no local backend). `TOKEN_STORE_BACKEND=memory` until the org-policy key unblock (see A1). |
| A2 | Background sync + incremental sync | **DONE** (`295d59f`, audited PASS): POST /sync = 202 background task + GET /sync/status; already-synced ids skipped BEFORE Claude (re-syncs ~free). Periodic APScheduler auto-sync deliberately deferred to the FCM phase. |
| A3 | Extraction hardening: tool-use/structured output (also fixes the raw_text log nit), model review, Batch API backfill, **rate limiting** (A2 audit: repeated POST /sync still triggers a full 30-day metadata scan each time — cost vector; also the in-process status registry has no eviction, bounded by user count) | next backend item |
| B | Android OAuth client (SHA-1 `8B:E8:14:1C:…`) → app on Android; Firebase/FCM sender + APNs (D22/D26/D27) | needs console/accounts (user) |
| **E0** | **Google OAuth verification** — restricted `gmail.readonly` scope: Limited-Use compliance + annual CASA assessment. Long lead time; start once deployed. Prereq for leaving Testing mode AND for ads | after C |
| E | Ad layer (D19/D21: in-house/static + AdMob npa=1, firewalled) + Stripe ad-free tier | ONLY after E0 ("ships and verifies") |
| F | Encrypted family vault (photos, reports, vaccination cards) | later phase, own design cycle (locked scope boundary) |
| D | App polish: calendar view, sync-progress UX, settings/delete-account | anytime |

Hygiene queue: remove deprecated `blocked_domains.json` (Phase 2); decide fate of the legacy
no-JWT web callback in `oauth.py`.

> **Update 2026-06-24 — Frontend mobile sign-in wired to the backend.** Flutter app now does the
> D23 flow: `google_sign_in` 7.x → serverAuthCode → `POST /api/v1/auth/google/mobile` → store the
> app JWT (secure storage; Gmail tokens stay server-side, D4). New: `auth/google_auth_codes.dart`
> (plugin boundary, testable), `auth/auth_service.dart`, `auth/session_controller.dart`,
> `ui/sign_in_screen.dart` + `ui/home_screen.dart`; `app.dart` gates on session via `AuthGate`;
> `ProviderScope` moved to `main.dart`. **`flutter analyze` clean; 13 tests pass.**
> **Native config still required before a real device sign-in works** (console/Xcode, not code):
> 1. **Build-time:** `--dart-define=GOOGLE_SERVER_CLIENT_ID=<WEB OAuth client id>` and
>    `--dart-define=API_BASE_URL=<backend url>`.
> 2. **iOS:** create an iOS OAuth client; set `GIDClientID` (iOS client id) + add its reversed-client-id
>    as a URL scheme in `ios/Runner/Info.plist`.
> 3. **Android:** register the app's SHA-1 against an Android OAuth client in the same GCP project.
> 4. Confirm the backend `exchange_server_auth_code` `redirect_uri` against the real client (often
>    `''`/`postmessage` for the offline-code flow) on the first device test.

---

## What Mamaflow Does

Mamaflow connects to a parent's Gmail, reads family-related emails (school, doctors, activities, playdates), and extracts structured calendar events **and action items** using Claude. It filters noise, redacts PII, defends against prompt injection, and returns clean JSON.

---

## Pipeline (4 layers, all working)

```
Gmail OAuth → fetch_recent_emails (last 30 days, max 50)
  → Layer 1: Sender blocklist (PostgreSQL — allowlist wins, then blocklist, then unknown passes through)
  → Layer 2: Presidio PII redaction (credit cards, bank accounts, SSNs, IBANs, Canadian SINs)
  → Layer 3: Nonce-tagged prompt injection wrapper (randomized delimiters + Unicode escaping)
  → Claude Sonnet 4.6 extraction → structured FamilyItem JSON (events + actions)
```

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check |
| GET | `/api/v1/auth/google` | Start Gmail OAuth flow |
| GET | `/api/v1/auth/google/callback` | OAuth callback |
| GET | `/api/v1/sync/preview?email=` | Raw email list (no filtering) |
| GET | `/api/v1/sync/preview-filtered?email=` | Emails sorted into allowed/blocked/unknown with PII redaction |
| GET | `/api/v1/sync/extract?email=` | Full pipeline — returns structured events + actions per email |

---

## Extraction Schema (FamilyItem)

Each extracted item is either an **event** (has a date/time) or a standalone **action** (a to-do with no date):

```json
{
  "item_type": "event | action",
  "event_title": "Charlie's appointment at Grandview",
  "action_required": "Call Grandview to confirm before June 19",
  "date": "2026-06-19",
  "time": "10:00 AM",
  "location": "Grandview Medical Centre",
  "child_name": "Charlie",
  "event_type": "medical",
  "source_sender": "reception@grandview.ca",
  "source_email_link": "https://mail.google.com/mail/u/0/#inbox/19abc123"
}
```

- **item_type "event"**: has a date/time. May also carry `action_required` (e.g. "RSVP by Friday").
- **item_type "action"**: standalone to-do with no date (e.g. a registration link). `event_title` may be null.
- **source_email_link**: Gmail deep link, stamped server-side from `message_id` — never from Claude output.
- **additionalProperties: false** enforced — locked schema doubles as injection defense.

---

## Privacy Posture

The pipeline makes a deliberate distinction between **harm-class PII** (always redacted) and **contextual PII** (preserved by design):

**Always redacted (Layer 2 — Presidio):**
- Credit card numbers
- Bank account numbers (US + IBAN)
- Social Security numbers (US SSN)
- Social Insurance numbers (Canadian SIN)
- Generic account-number patterns (`Account #: 12345678`)

**Intentionally preserved:**
- Phone numbers — needed in school/doctor contacts ("call the office at 416-555-1234")
- Dates of birth — needed for age-appropriate event context
- Names — needed for child attribution (`child_name` field)
- Addresses — needed for event locations

**Structural defenses (no PII reaches the wrong layer):**
- Financial sender domains blocked at Layer 1 *before the email body is ever fetched*
- Raw email body is never stored in the database (processed in-memory only)
- OAuth tokens never stored in the database (in-memory for Phase 0, Secret Manager for prod)
- All content wrapped in nonce-tagged boundaries before Claude sees it (Layer 3)

---

## File Map

> Restructured 2026-06-22: all backend code now lives under `backend/` (package still `api`, imports
> unchanged). Run all commands from `backend/`. `backend/` also holds `alembic/`, `alembic.ini`,
> `requirements.txt`, `tests/`, `.env.example`. AI-assistant config + firewall guard live at the repo
> root (`AGENTS.md`, `.claude/`, `.agents/`, `scripts/`, `.githooks/`; see `AI-SETUP.md`).

```
backend/api/
├── main.py                         # FastAPI app + lifespan
├── auth/
│   ├── oauth.py                    # Google OAuth with PKCE
│   └── token_store.py              # In-memory token storage (Phase 0)
├── config/
│   ├── settings.py                 # Pydantic Settings (env vars)
│   └── blocked_domains.json        # DEPRECATED — DB is source of truth
├── db/
│   ├── session.py                  # Async SQLAlchemy engine + get_db dependency
│   └── seed.py                     # Idempotent blocklist seed (python -m api.db.seed)
├── models/
│   ├── base.py                     # Base + TimestampMixin (UUID PK, timestamps, soft delete)
│   ├── sender_allowlist.py         # SenderAllowlist model
│   └── sender_blocklist.py         # SenderBlocklist model (CHECK constraint on category)
├── routers/
│   └── sync.py                     # /preview, /preview-filtered, /extract endpoints
├── schemas/
│   ├── email.py                    # EmailPreview, BlockedEmail, FilteredPreview, ExtractionPreview
│   ├── blocklist.py                # BlocklistResult (allowed/blocked/unknown)
│   └── family_event.py             # FamilyItem (event|action) + ExtractionResponse (locked output schema)
└── services/
    ├── gmail_reader.py             # Gmail API client, fetches last 30 days
    ├── sender_blocklist.py         # Layer 1 — async DB queries (allowlist → blocklist → unknown)
    ├── privacy_pipeline.py         # Layer 2 — Presidio PII redaction (5 entity types + 3 custom recognizers)
    ├── content_wrapper.py          # Layer 3 — Nonce-delimited injection defense + extraction prompt
    └── ai_extractor.py             # Claude Sonnet 4.6 API call + JSON parsing

backend/alembic/
├── env.py                          # Async migration runner
└── versions/
    └── f11c1892443a_create_sender_allowlist_and_sender_.py

backend/tests/
└── test_content_wrapper.py         # 7 security tests for prompt injection defense
```

---

## Environment Setup

1. Copy `backend/.env.example` to `backend/.env` and fill in real values:
   - `DATABASE_URL` — Railway PostgreSQL connection string (standard `postgresql://` prefix; the app converts to `postgresql+asyncpg://` at runtime)
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — GCP OAuth 2.0 credentials with Gmail readonly scope
   - `ANTHROPIC_API_KEY` — Anthropic API key for Claude Sonnet 4.6
2. `cd backend && pip install -r requirements.txt` — run all commands below from `backend/`
3. `python -m alembic upgrade head` — creates sender_allowlist and sender_blocklist tables
4. `python -m api.db.seed` — inserts 27 default blocklist rows (idempotent)
5. `uvicorn api.main:app --reload` — starts the server on port 8000
6. Navigate to `http://localhost:8000/api/v1/auth/google` to authenticate
7. Hit `http://localhost:8000/api/v1/sync/extract?email=YOUR_EMAIL` for full extraction

---

## Key Architectural Decisions

- **Shim/broker split** (D2): Email shim is public-facing, never holds credentials. Email broker is private, holds OAuth tokens, runs the privacy pipeline. Not yet split into separate services in Phase 0 — currently a single FastAPI app.
- **Tokens never in DB** (D4): OAuth tokens are in-memory for Phase 0. Production moves to Secret Manager references.
- **Raw body never stored** (D5): Email bodies are processed in-memory and never written to the database.
- **Sender blocklist is structural** (D13): Not a user-facing setting. Managed via DB seed + admin.
- **Wrap-by-default injection defense** (D3): Every email body is wrapped in randomized nonce-tagged boundaries before Claude sees it.

---

## Known Deferred Items

| Item | Why Deferred | When |
|------|-------------|------|
| `fetch_recent_emails` is synchronous | Blocks event loop. Wrap in `run_in_executor` or use `httpx` async. | Phase 1 |
| Token storage is in-memory | Tokens lost on restart. Move to Secret Manager references. | Phase 1 |
| No user model / auth middleware | All endpoints take `email` as a query param. Real auth needed. | Phase 1 |
| `updated_at` is client-side `onupdate` | Raw SQL updates won't trigger it. Add PG trigger if needed. | Phase 1 |
| SSN detection needs spaCy `en_core_web_lg` | Custom recognizer works but the built-in one underperforms without the large model. | Phase 1 |
| No rate limiting on `/extract` | Each call hits Claude API per email. Add throttling before production. | Phase 1 |
| `blocked_domains.json` still in repo | Deprecated — DB is source of truth. Remove file in Phase 2. | Phase 2 |
| Shim/broker service split | Currently one FastAPI app. Split when deploying to production. | Phase 2 |

---

## Where Phase 1 Starts

Phase 0 proved the pipeline works end-to-end on real emails. Phase 1 builds the product:

1. **User model + auth middleware** — JWT-based sessions, user_id on all tables
2. **Event persistence** — store extracted FamilyEvent rows in PostgreSQL
3. **Incremental sync** — track last-synced message ID, process only new emails
4. **Background processing** — move extraction off the request path (task queue or background worker)
5. **Error handling + retries** — Claude API failures, Gmail token refresh, partial extraction

See `CLAUDE.md` for the full architecture and decision log.

---

## Commit History

```
3a8e695 feat: extract action items alongside events from emails
7408080 docs: add developer handoff for Phase 0
e7a041a feat: Claude extraction endpoint — full pipeline end-to-end
c5f28e2 feat: wrap-by-default prompt injection defense (Layer 3)
f071da1 feat: Presidio PII redaction (Layer 2 of privacy pipeline)
2e62c06 feat: PostgreSQL sender filter with allowlist + blocklist tables
07a5ff3 feat: add sender blocklist with JSON-based blocked domains
32af9c9 feat: Gmail reader with preview endpoint for last 30 days of inbox
3352ff6 feat: Gmail OAuth flow with PKCE, GCP project scaffolding
```
