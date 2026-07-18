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

> **Update 2026-07-10 — Full code audit (firewall + backend + frontend), read-only.** Three parallel
> audits (security-auditor, code-reviewer, frontend) against the whole repo. **Firewall/privacy: PASS,
> no BLOCKs** — all five flows clean (content→ads, raw-body persistence, tokens, metadata-first fetch
> ordering, injection wrap); firewall-guard exit 0; backend **111 tests pass**, no live-API calls in
> tests. **2 must-fix before Track B push activation:**
> 1. Stale FCM registration on account switch/sign-out (`push_service.dart` `_started` guard on an
>    app-lifetime singleton + no unregister endpoint) — user A's content-bearing digests can reach
>    user B's lock screen on a shared device.
> 2. 15-min JWT with no client refresh flow — any session >15 min gets dumped to sign-in mid-action
>    (401 → auto sign-out). Decide: refresh flow vs longer TTL.
>
> Top should-fixes: reminder digest sorts free-form `event_time` strings lexicographically
> (`reminders.py:43`, "9:00 AM" after "2:30 PM"); unhandled base64 decode in `gmail_reader.py:42`
> fails a whole sync on one malformed message; legacy GET `/preview`/`/preview-filtered`/`/extract`
> have no cooldown + return redacted body text (unused by the app — remove or gate); legacy web OAuth
> callback (`oauth.py`) has KeyError→500 paths + blocking sync I/O on the loop; ad-isolation test is
> one-directional (nothing stops a feature file importing `google_mobile_ads` directly); no Dio
> timeouts; one malformed item row breaks the whole items list (hard `as` casts); privacy policy
> missing Firebase/FCM sub-processor row; `apscheduler`/`firebase-admin` unpinned in requirements.
> Full findings in the audit report (PM conversation 2026-07-10).
>
> **Fix batch landed same day (7 commits, security-audited PASS, no BLOCKs).** Backend **133** tests,
> frontend **66**, `flutter analyze` clean:
> 1. **M1 FIXED** — `POST /api/v1/devices/unregister` (soft-delete, user-scoped, idempotent, no
>    enumeration oracle); frontend `PushService.stop()` unregisters + cancels the token-refresh
>    listener + resets the start guard; `SessionController.signOut()` stops push BEFORE clearing the
>    JWT; the 401 handler resets locally only (no network → no 401 loop).
> 2. **M2 FIXED (D31)** — session JWT TTL default now **30 days** (43200). ⚠️ **USER: update
>    `ACCESS_TOKEN_EXPIRE_MINUTES=43200` on Railway AND in your local `backend/.env`** (the old 15 is
>    still in both; `.env` overrides the new default).
> 3. Privacy policy: Firebase/FCM sub-processor row added (content-derived digest text disclosed).
> 4. Reminder digest sorts by parsed wall-clock time (`_time_key`), untimed last.
> 5. `gmail_reader` hardened: malformed base64/MIME/headers degrade to "" per message (new
>    `test_gmail_reader.py`) — one bad email can no longer fail a sync batch.
> 6. Debug `GET /sync/preview|preview-filtered|/extract` **REMOVED** (+ their schemas). Hygiene-queue
>    item resolved the other way: the legacy web OAuth callback was **hardened, kept for dev**
>    (deny/missing/unknown state → 400, token exchange + cert fetch off-loop, pending-state dict
>    bounded, types-only logging in the mobile exchange).
> - Audit WARNs tracked, not fixed: unauthenticated `GET /google` can FIFO-evict in-flight web-OAuth
>   states (DoS-only, legacy flow — rate-limit or TTL-evict before real web traffic);
>   `docs/backend-requirements-from-frontend.md` + the 2026-06-22 Flutter spec still mention the
>   removed GET endpoints (doc hygiene).
> - **Should-fix batch DONE same day (5 more commits, security-audited PASS, no BLOCKs).** Backend
>   **134** tests, frontend **82**, analyze clean: Dio timeouts (`buildDio`) + fail-loud
>   https-only `API_BASE_URL` in release (`resolveBaseUrl`); `Item.tryParse` skips malformed rows;
>   status mutations awaited + snackbar on failure (detail pops only on success); session flip →
>   pop pushed routes to root (`rootNavigatorKey`); OAuth `state` param (RFC 8252, fail-closed) +
>   consent-sheet cancel returns null quietly (`signInWithGoogle`/`signIn` now nullable);
>   ad-isolation test now bidirectional (SDK only under `lib/ads/`, `lib/ads/` app/content-free,
>   case-insensitive); `apscheduler>=3.11,<4` + `firebase-admin>=7.5.0` pinned; `.env.example`
>   documents `SYNC_COOLDOWN_SECONDS`, dead Stripe placeholders dropped (return with Track E);
>   `get_or_create_user` recovers from the concurrent first-sign-in IntegrityError.
> - Accepted low-priority follow-ups (audit WARNs, deliberately not done): a drop-counter/log for
>   `Item.tryParse` (the app is deliberately log-free); narrowing the IntegrityError catch if more
>   unique constraints are ever added to `users`; rate-limit/TTL-evict `GET /google` state (above).

> **Update 2026-07-14 — Android OAuth + FCM registration E2E VERIFIED on emulator against prod.**
> Full round-trip on the Pixel emulator against `https://mamaflow-production.up.railway.app`:
> Continue with Google → browser PKCE flow (account chooser → tester interstitial → consent incl.
> the Gmail-scope checkbox) → redirect into the app (`CallbackActivity`) → backend code exchange →
> signed-in Agenda → notification permission granted (`POST_NOTIFICATIONS granted=true`) →
> `PushService` token registration ran (no failure logged). Two days of "Sign-in failed" were
> **environment, not code**: (1) the emulator's default DNS could not resolve `*.up.railway.app`
> (Google domains resolved fine) → every token-exchange POST died as `DioException [unknown]` —
> fixed by launching the emulator with `-dns-server 8.8.8.8,1.1.1.1`; (2) Chrome rendered blank
> pages under the emulator's hardware GPU → `-gpu swiftshader_indirect`. **Emulator testing needs
> both flags:** `emulator -avd <name> -gpu swiftshader_indirect -dns-server 8.8.8.8,1.1.1.1`.
> Also required en route: `sabiranthapa5@gmail.com` added to the OAuth **Test users** list (a
> non-tester gets a hard "Access blocked: 403 access_denied" with no Advanced link), and stale
> half-added device Google accounts removed ("This account already exists on your device" blocks
> Google's embedded add-account flow — sign in via the app's own tab instead). Debug-only
> diagnostic added: `sign_in_screen` now `debugPrint`s the sign-in exception type (was a blind
> `catch (_)` — cost hours). **Still to verify (USER, prod-DB read):** the `devices` row for the
> new registration, then the live digest test (`REMINDER_HOUR` nudge + an open event dated
> tomorrow).

> **Update 2026-07-15 — 🚀 TRACK B VERIFIED LIVE END-TO-END.** The evening-before digest
> ("Tomorrow's schedule — Doctor Appointment 11:00 AM") was delivered to the Android emulator's
> notification shade at 12:00:00, one second after the APScheduler tick, from the production
> backend: Gmail → OAuth → blocklist → Presidio → Claude → Postgres → tick → digest → FCM → shade.
> Getting there surfaced and fixed three prod bugs (all merged to main, PR #8/#9):
> 1. **REMINDER_HOUR="10:30" took the whole API down** (pydantic int validation fails at import →
>    502 for everything). Reminder knobs (`REMINDER_HOUR`/`REMINDER_TZ`) are now fail-soft:
>    bad values fall back to defaults with a warning; SECRET_KEY still fails hard. REMINDER_HOUR
>    must be a whole hour 0-23 (documented in .env.example).
> 2. **Every prod extraction had silently 400'd since the A3 strict-tool-use change**: Anthropic's
>    strict mode rejects `enum` combined with a union type ("Enum value 'school' does not match
>    declared type ['string','null']"). Mocked tests can't catch real API schema validation —
>    found by running one real extraction locally. `event_type` is now `anyOf` (same vocabulary +
>    null). Verified live: 36 messages scanned, soccer/dentist/doctor test emails all extracted
>    with correct ISO dates and categories.
> 3. **One failing message killed the whole sync job** — the loop now isolates per-message failures
>    (skip + types-only log + rollback + user re-fetch after rollback, the MissingGreenlet twin of
>    the reminder-engine Critical). A failed message writes no items row, so it retries next sync.
> Also: frontend Dio connectTimeout 10s→30s (emulator NAT + slow cellular exceed 10s on cold TLS
> connect). Known emulator-only wart: after OAuth consent the Custom Tab stays on a leftover
> google.com page instead of auto-closing (the app gets the callback and signs in fine —
> verified redirect works on real iPhone; re-check on a real Android device).
> **USER: set REMINDER_HOUR back to 18 on Railway** (it's 12 from the test) and update
> `ACCESS_TOKEN_EXPIRE_MINUTES=43200` (still 15 — sessions expire mid-testing constantly).

> **Auto-sync shipped 2026-07-16:** hourly background sync per signed-in user at minute :30
> (reminders stay at :00, so the 18:00 digest reads data ≤30 min old). One sync implementation
> (`services/sync_runner.py`, moved from the router) shared by POST /sync and the tick;
> `sync_state.try_start` gates both (no double-runs; manual cooldown honored). Kill switch
> `AUTO_SYNC_ENABLED` (default true, fail-soft). Users without a stored Gmail token are skipped —
> universal coverage arrives when A1 (Secret Manager) is flipped on. Supersedes the A2 row's
> "periodic auto-sync deferred" note. Spec/plan: docs/superpowers/{specs,plans}/2026-07-15-auto-sync*.

> **Update 2026-07-17 — 🔐 A1 DONE (durable Gmail tokens) — LIVE + VERIFIED, plus a critical
> latent-bug fix it exposed.** Secret Manager token store activated on Railway (`TOKEN_STORE_BACKEND=
> secret-manager`, `GCP_PROJECT_ID=mamaflow-prod`, `GOOGLE_APPLICATION_CREDENTIALS_JSON` = the
> `mamaflow-backend` SA key; the env-JSON credentials path shipped so Railway needs no ADC file).
> Proven end-to-end: a Gmail token survived a backend restart and was read back from Secret Manager
> — the re-sign-in-after-every-deploy era is over. **Durability immediately exposed a
> production-critical latent bug:** mobile sign-in stores `client_secret=None` (iOS public client,
> D23/D28), but google-auth's `Credentials.refresh()` refuses to refresh without a secret, so every
> Gmail call failed once the ~1h access token expired. In-memory storage had hidden it (tokens never
> outlived the access token) — every real user would have broken ~1h after signing in. **Fixed**
> (`services/google_token.py` `ensure_fresh`: public-client refresh — client_id + refresh_token, no
> secret, RFC 6749 §6 — re-stores the fresh token to Secret Manager; sign-in now stamps `expiry`;
> revoked/absent → `ReauthRequired` → "Please sign in again"; Google 5xx → transient retry). Security
> audit PASS (ReauthRequired carries no PII; types-only logs). 163 backend tests. Verified on
> emulator: a >1h-old token that failed pre-fix refreshed and synced clean post-deploy. Commits: A1
> env-JSON `c98d4b0`, refresh fix `85912d2`. Docs: `docs/a1-secret-manager-activation.md`.

 **Update 2026-07-17 — Ad prototype (UX + build verification):** firewalled AdMob TEST banner anchored bottom of the shell,
> gated by --dart-define=SHOW_ADS=true (off by default). Testers see ads working via test
> creatives — no account, no cost, no ban risk. Real serving is a launch-time swap (real ids +
> app-ads.txt at the E0 domain + published app + privacy-policy AdMob row). Build the tester
> distribution WITH the flag; everyday builds omit it and behave as today.

> **Update 2026-07-17 — UI redesign: warm & friendly ("Mama Coral").** The app was baseline-purple
> Material 3 with zero theme; it now has a cohesive design system + redesigned Agenda & Calendar.
> Plan `docs/superpowers/plans/2026-07-17-ui-redesign.md`. Presentation-only — grouping/filters/
> providers and every find-by-text test contract untouched; 90 frontend tests green, `flutter analyze`
> clean; firewall guard 0 (no `lib/ads/` change). **Foundation** (`lib/theme/`): `tokens.dart`
> (spacing/radii/shadow/motion), `app_colors.dart` (`ColorScheme.fromSeed(#F27E63)` + warm cream
> surfaces), `category_colors.dart` (event-type → color+icon, deterministic fallback), `app_theme.dart`
> (light theme + all component themes + app-wide fade/slide page transitions; dark theme is a stubbed
> fast-follow, ships **light-only**). Fonts: **Nunito** (body) + **Fredoka** (headlines/wordmark),
> bundled variable TTFs in `assets/fonts/` (offline — `google_fonts` intentionally dropped, no runtime
> fetch, fits the privacy stance). Dep added: `flutter_animate`. **Shared components** (`lib/ui/widgets/`):
> `ItemCard` (category badge + meta pills + swipe done/dismiss with haptics + one-shot staggered
> entrance; `interactive:false` for the calendar), `SectionHeader`, `FilterChipBar` (animated select),
> `EmptyState`/`ErrorState`/`LoadingState`, `SyncProgressCard`. Agenda & Calendar rewired onto them;
> calendar gained category-colored day dots + warm animated cells + a dense day list. **Documented
> fast-follow (out of scope):** per-screen polish for sign-in/item-detail/settings (they inherit the
> theme now), dark theme, launcher-icon rebrand. Foundation `108e4f5..881dd89`; components+screens+motion
> `881dd89..c5095ca`. **USER: on-device eyeball pending** (`flutter run` + `--dart-define=SHOW_ADS=true`
> to confirm the coral theme, category dots, staggered entrance, swipe+haptics, and that the ad slot
> still lays out below content).

> **Update 2026-07-17 — Branding: logo + landing/sign-in + splash + launcher icon.** Plan
> `docs/superpowers/plans/2026-07-17-branding-logo-landing-splash.md`, spec
> `docs/superpowers/specs/2026-07-17-branding-logo-landing-splash-design.md`. The heart-in-bubble
> `AppLogo` (vector) now brands: the redesigned sign-in/landing (logo + Fredoka wordmark + three
> trust lines + in-button loading), an in-app hydrate splash (`BrandSplash`), the native launch
> screen (coral + logo, iOS + Android 12), and the launcher icon (iOS + Android adaptive) — killing
> the default Flutter icon/splash before the tester distribution. Master PNGs are generated from the
> same painter (`tool/generate_brand_assets.dart`) so nothing drifts. Presentation/config only;
> firewall untouched; sign-in test invariants preserved. **USER: rebuild on device to see the new
> icon/splash** (native assets only appear on a fresh install/run).

> **Update 2026-07-18 — Full backend maintainability audit (code-maintainability-audit skill) +
> event-loop fix batch.** Three parallel audits (async/parsing, Pydantic/UUID-UTC/soft-delete,
> secrets/deps/errors) over `backend/api/`. Clean: IDs & time, soft delete, secrets (env 1:1 with
> `.env.example`, tokens never in DB/logs, nothing in git history), deps (all used, pinned),
> error hygiene (types-only logging holds everywhere), defensive parsing (extractor/gmail/token/FCM).
> **Fixed same day (TDD, security-audited PASS, 167 backend tests):** all four blocking-call
> findings wrapped in `asyncio.to_thread` — `redact_pii` in the sync loop (must-fix: Presidio is
> CPU-bound; stalled every concurrent request during a sync), `token_store.get/delete_token` in
> `delete_account`, and `store_token` in both OAuth handlers (blocking Secret Manager gRPC in the
> sign-in hot path). Four regression tests assert these run off the loop thread.
> **Remaining should-fix (not done):** `FamilyItem.event_type` is `str|None`, not `Literal` — since
> the 2026-07-15 `anyOf` fix removed the strict-schema enum coupling, no layer (Pydantic or DB CHECK)
> enforces the vocabulary; `?type=` on GET /items not `Literal` (typo → empty 200, not 422);
> `google_callback` returns a raw dict (no response schema); no `pip-audit` in CI. Nits queued:
> `msg["id"]` direct indexing in gmail_reader (whole-batch failure vs per-message isolation),
> `ItemRead.item_type/status` not `Literal`, delete `blocked_domains.json` (already in hygiene queue).

| Track | What | Gate / status |
|-------|------|---------------|
| A1 | Persistent Gmail tokens — **Secret Manager** (D4 forbids DB storage, even encrypted); in-memory stays the dev default | **Code DONE** (`cbbbe71`+`01a89ce`, audited PASS). **User-side BLOCKED**: the `optimacore.io` org enforces `iam.disableServiceAccountKeyCreation` (Secure-by-Default), so the service-account JSON key can't be created yet. **Plan:** deploy Railway with `TOKEN_STORE_BACKEND=memory` now (re-sign-in after each restart — acceptable in Testing); later an org admin (Sabiran/Akhil with `roles/orgpolicy.policyAdmin`, granted at the ORG level) creates a **project-scoped override** (Mamaflow project → IAM & Admin → Organization Policies → "Disable service account key creation" → Override parent → Enforcement Off), then creates the key (svc acct `mamaflow-backend`, role Secret Manager Admin) and flips the Railway vars (`TOKEN_STORE_BACKEND=secret-manager`, `GCP_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`). No code change needed. Keyless alternative if this drags: host backend in GCP (Cloud Run attaches the svc acct without any key). |
| C | Deploy backend to Railway (Dockerfile, https, prod SECRET_KEY; kills dev ATS/cleartext exceptions). ⚠️ Audit flag: the token store's in-process cache is NOT multi-instance coherent — instance A's token refresh won't invalidate instance B's cache. Single instance only until a TTL/invalidation hook lands. | **DONE 2026-07-03** — live at https://mamaflow-production.up.railway.app (health/routes/auth verified; **full-cloud E2E from iPhone confirmed**: sign-in → sync → items, no local backend). `TOKEN_STORE_BACKEND=memory` until the org-policy key unblock (see A1). |
| A2 | Background sync + incremental sync | **DONE** (`295d59f`, audited PASS): POST /sync = 202 background task + GET /sync/status; already-synced ids skipped BEFORE Claude (re-syncs ~free). Periodic APScheduler auto-sync deliberately deferred to the FCM phase. |
| A3 | Extraction hardening + rate limiting | **DONE** (`f9c5157`): strict tool-use extraction (schema-guaranteed output, raw_text log leak killed, server-side link stamping test-proven); per-user sync cooldown (`SYNC_COOLDOWN_SECONDS`=60 → 429+Retry-After; app shows friendly message). Remaining from the line item: **model review pending PM** (keep `claude-sonnet-4-6` vs Sonnet 5 vs Haiku-4.5 cost eval); Batch API backfill deferred until scale; status-registry eviction nit (bounded by user count). |
| B | Android sign-in + Firebase/FCM sender + APNs (D22/D26/D27) | **Sign-in DONE 2026-07-04 (code)** — D30: Android **reuses the iOS OAuth client** (no separate Android client / SHA-1 needed for auth). Registered the `flutter_web_auth_2` `CallbackActivity` with the reversed-iOS scheme in `frontend/android/app/src/main/AndroidManifest.xml`; app takes the same `--dart-define=GOOGLE_IOS_CLIENT_ID`. **Verified on an Android emulator 2026-07-04 (API 37):** app builds, launches to the sign-in screen, and "Continue with Google" hands off to the browser/Custom-Tab OAuth flow (no crash, OAuth URL built). Running it surfaced + fixed **two pre-existing Android build gaps** (iOS-only until now): core library desugaring for `flutter_local_notifications`, and the AdMob `APPLICATION_ID` meta-data (google_mobile_ads' startup ContentProvider crashes without it) — both in `android/app/build.gradle.kts` + `AndroidManifest.xml` (test ids, replace before release). **USER: still do the real Google login round-trip on a device/emulator** with a test-user account (`flutter run -d <android> --dart-define=API_BASE_URL=https://mamaflow-production.up.railway.app --dart-define=GOOGLE_IOS_CLIENT_ID=<ios client id>`) to confirm the redirect back into the app. **Reminder engine DONE 2026-07-04 (backend, INERT).** The FCM push sender (`firebase-admin`, prunes dead tokens), reminder selection + **evening-before digest**, and an hourly APScheduler job (wired into the lifespan, per-user daily dedup via `users.last_reminder_date`) are built + tested (backend now 111 tests) — but **dark until `FIREBASE_CREDENTIALS_JSON` is set** (the A1 pattern: no sender, no scheduler started when unset, so the app runs as today). Per-task + whole-feature security audit PASS (credential env-only never DB/logged, digest only to FCM never the ad layer, scoped queries, soft-delete prune). Config: `FIREBASE_CREDENTIALS_JSON`/`REMINDER_TZ`(default America/Toronto)/`REMINDER_HOUR`(18). **Still gated (USER):** create a Firebase project + register the iOS/Android apps (Android package + SHA-1 `8B:E8:14:1C:8C:E8:73:1F:EB:2D:52:1A:8B:EF:4A:67:7C:D1:B8:B9`) → `google-services.json`/`GoogleService-Info.plist`, an APNs key, and a service account → set `FIREBASE_CREDENTIALS_JSON` + run the `d4e3f2a1b0c9` migration. **Frontend Firebase wiring DONE 2026-07-09 (code, emulator-verified):** `google-services.json`/`GoogleService-Info.plist` placed (both **gitignored** — must be re-added on any fresh clone/CI), `com.google.gms.google-services` Gradle plugin, `Firebase.initializeApp()` in `main.dart` (best-effort), and `lib/push/push_service.dart` (permission → FCM token → register via existing `DeviceRegistrar` → token-refresh listener), triggered from `HomeShell.initState` after sign-in. Debug APK **built + launched on Android emulator (API 37): no crash, `FirebaseApp initialization successful`**; 54 frontend tests pass, `flutter analyze` clean. Security audit **PASS** (only fcm_token+platform leave the device; push structurally isolated from the ad SDK). **Remaining manual step (iOS only):** drag `ios/Runner/GoogleService-Info.plist` into the Runner target in Xcode (objectVersion 54 = no auto-include) before the first iOS/TestFlight build. Token-fetch+register leg verifies on-device once you sign in with a test user against the running backend. Full steps: `docs/track-b-push-activation.md`. Known MVP limitation: fixed-timezone reminders (per-device tz is a follow-up). |
| **E0** | **Google OAuth verification** — restricted `gmail.readonly` scope: Limited-Use compliance + annual CASA assessment. Long lead time; start once deployed. Prereq for leaving Testing mode AND for ads | after C |
| E | Ad layer (D19/D21: in-house/static + AdMob npa=1, firewalled) + Stripe ad-free tier | ONLY after E0 ("ships and verifies") |
| F | Encrypted family vault (photos, reports, vaccination cards) | later phase, own design cycle (locked scope boundary) |
| D | App polish: calendar view, sync-progress UX, settings/delete-account | **Slice 1 DONE 2026-07-04** — "Useful items view": grouped agenda home (Overdue / Today / This week / Later / To-do), client-side child/type filter chips, tappable item-detail screen (opens the source email via `url_launcher`, https-only), and a `?status=` filter on `GET /items` with a "Show completed" toggle (open→done; dismissed stay hidden). Spec `docs/superpowers/specs/2026-07-04-useful-items-view-design.md`, plan `docs/superpowers/plans/2026-07-04-useful-items-view.md`. Backend 72 tests, frontend 41; per-task + whole-feature security audit PASS (firewall/D5/D4 clean; https launcher guard added). **Slice 2 DONE 2026-07-04** — "Settings + delete-account" (also an E0/OAuth-verification prereq: a working data-deletion path). Backend: `DELETE /api/v1/account` (`api/services/account.py`) soft-deletes the user + their items + devices in one commit (scoped to the authed user, never a hard delete), then **revokes the Gmail token at Google** (`revoke_gmail_token`, best-effort, off the event loop via `asyncio.to_thread`) and drops it from the store — a revoke failure never blocks the delete, no token is ever logged; `token_store.delete_token` (both backends); `get_or_create_user` now **reactivates** a soft-deleted user on re-sign-in (unique email — a reactivated account starts empty, old rows stay soft-deleted); a retained JWT for a deleted account already 401s via `get_current_user`'s `deleted_at` guard. Frontend: a **Settings** screen (gear on home; sign-out moved here) showing the account email (decoded from the session JWT), with **type-to-confirm ("DELETE")** account deletion → `DELETE /account` → sign out. Spec/plan `docs/superpowers/{specs,plans}/2026-07-04-settings-delete-account*.md`. Backend 84 tests, frontend 47; per-task + whole-feature security audit PASS (delete scoping, token never logged, revoke off-loop, reactivation can't surface prior data, firewall untouched). Privacy-policy row deferred until E0 hosts a URL. **Slice 3 DONE 2026-07-04 — TRACK D COMPLETE.** "Finish Track D": (A0) hardened `normalize_item_date` to strip a bundled trailing time (e.g. "July 5th (Saturday) 10:00 AM"→ISO) + an idempotent **user-run backfill** `python -m api.db.backfill_dates` that re-normalizes stored prose `event_date` values in place (string only — never re-fetches/re-extracts; skips ISO/unparseable/soft-deleted) — **⚠️ USER ACTION: run `python -m api.db.backfill_dates` against Railway** to fix existing prose-dated items (e.g. the Soccer Practice test item) so they appear on the calendar. (A) **Month calendar tab** — bottom-nav shell (Agenda | Calendar), dependency-free month grid with dots on item days, prev/next + Today, tap-a-day → that day's items → detail; dateless to-dos stay in Agenda. (B) **Live sync progress** — the background job emits counts mid-run (`to_process` + incremental `processed` on `sync_state`/`/sync/status`), and the app shows a determinate progress card ("Scanned N · processed X/Y · Z items") replacing the snackbar. Spec/plan `docs/superpowers/{specs,plans}/2026-07-04-finish-track-d*.md`. Backend 92 tests, frontend 53; per-task + whole-feature security audit PASS (backfill touches only the event_date string, sync progress writes only integer counters, calendar/card read already-loaded items — firewall/D5/D4 clean). |

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
| GET | `/api/v1/auth/google` (+ `/callback`) | Legacy web OAuth (dev-only; hardened 2026-07-10) |
| POST | `/api/v1/auth/google/mobile` | Mobile PKCE code exchange → app JWT (D28) |
| POST | `/api/v1/sync` (+ GET `/sync/status`) | Background sync (202 + poll); cooldown-limited |
| GET | `/api/v1/items` / PATCH `/api/v1/items/{id}` | List / update persisted items |
| POST | `/api/v1/devices/register` / `/unregister` | FCM device registration lifecycle |
| DELETE | `/api/v1/account` | Soft-delete account + revoke Gmail token |

_(The Phase-0 debug GETs `/sync/preview`, `/sync/preview-filtered`, `/sync/extract` were removed
2026-07-10 — no cooldown, returned redacted body text, unused by the app.)_

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
