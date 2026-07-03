# Frontend platform & foundation — Flutter (design)

**Date:** 2026-06-22
**Status:** Approved (design). Screen-by-screen UI deferred to a later brainstorm.
**Supersedes:** D9 / D20 ("PWA only — no App Store").

## Context

Mamaflow's frontend platform (D9/D20: "PWA only") was reopened because **push notifications /
reminders are core to the product** for busy parents, and a pure PWA can't deliver reliable iOS push
(iOS web-push only fires for "Add to Home Screen" installs). We confirmed two drivers:

- **Push is core at launch** → we must ship a real native app (APNs/FCM).
- **Mobile-first, web later** → the phone app is the product; a browser version is secondary.

Given the user has **prior Flutter/Dart experience** (so the "new language" cost is moot) and Flutter
offers a single mobile codebase with first-class AdMob support, **Flutter is the chosen platform**.
The goal of this spec is to lock the platform and define the foundation so the **backend direction
is clear** before building.

## Decision

- **Frontend = Flutter (Dart)**, mobile-first (iOS + Android). Web later via Flutter Web (app-style,
  deferred — not an SEO/marketing site).
- **Push = Firebase Cloud Messaging (FCM)** for both platforms (iOS via an APNs key in Firebase).
- **Auth = mobile Google OAuth** (serverAuthCode → backend token exchange). Gmail tokens stay
  server-side (D4); the app holds only its own session JWT.
- Decision-log updates to make during implementation: flip **D9/D20 → Flutter**; add **D22 = FCM
  push** and **D23 = mobile Google OAuth (auth-code exchange, tokens server-side)**.

## Drivers & constraints

- Push core at launch; mobile-first; web later.
- Team is productive in Flutter → maintainability + velocity.
- Monetization (D21): free + firewalled ads + paid ad-free tier; launch ads non-personalized AdMob
  (`npa=1`). AdMob is first-class in Flutter (`google_mobile_ads`).
- Firewall (D19): the ad layer is frontend-only and must never receive content/event/child data.
- Privacy (D4/D5): OAuth tokens never on device or in DB beyond server-side secret storage; raw email
  bodies never stored.

## Architecture & module boundaries

`frontend/` becomes a Flutter project. Units, each with one job + a clear interface:

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `api_client` | Thin REST/JSON client to FastAPI; auth interceptor; per-env base URL | `dio`, `auth` (for token) |
| `auth` | Google sign-in; stores ONLY the app's session JWT in `flutter_secure_storage` | `google_sign_in`, `api_client` |
| `push` | FCM device token + foreground local notifications; registers token with backend | `firebase_messaging`, `api_client` |
| `ads` | **Isolated** wrapper over `google_mobile_ads`; receives only allowed non-content signals | `google_mobile_ads` only |
| `features/*` | Calendar, todos, onboarding (UI designed in a later pass) | `api_client`, `auth` |

- **State management:** Riverpod. **Routing:** go_router. (Bloc is the considered alternative.)
- **Isolation rule:** `ads` has NO dependency on `features/*` models or any event/child/email data —
  this is the firewall expressed structurally.

## Auth flow (mobile Google OAuth)

1. App calls `google_sign_in` requesting **offline access + `gmail.readonly`**, obtaining a
   **serverAuthCode**.
2. App POSTs the code to a **new backend endpoint** (e.g. `POST /api/v1/auth/google/mobile`).
3. Backend exchanges it for Gmail access/refresh tokens (**held server-side** — in-memory for Phase 0,
   Secret Manager later, D4) and issues an **app session JWT** (PyJWT, already in stack).
4. App stores the JWT in secure storage; `api_client` attaches it to every request.

This replaces the current localhost web-redirect flow for mobile (the web flow can remain for dev).

## Push (FCM)

1. Device obtains an FCM token (`firebase_messaging`); foreground display via local notifications.
2. App sends the token to a **new `POST /api/v1/devices/register`** endpoint.
3. Backend stores the token per user and sends reminders via a **FCM sender service** (HTTP v1 API,
   service account).
4. iOS delivery requires an APNs key uploaded to Firebase. **Accepted trade-off:** more setup than a
   managed push service, but a single mature path for both platforms.

## Ads (firewall-safe)

- `google_mobile_ads`, **non-personalized (`npa=1`)** at launch per D21.
- The `ads` unit is structurally isolated; no content/event/child data crosses into it.
- **Extend `scripts/firewall-guard.sh` with Dart-aware ad patterns** (e.g. `*/ads/*.dart`,
  `*_ad.dart`, `*ad_*.dart`) so the deterministic guard still BLOCKs ad-layer files that reference
  `event`/`child`/`extraction`/email content — matching the existing React/Python heuristics.

## Backend direction this implies

This is the point of the spec — what the frontend choice requires of the backend. Several items
align with HANDOFF's "Where Phase 1 Starts":

- **Mobile OAuth exchange endpoint** (serverAuthCode → tokens + JWT) — *new*.
- **User model + JWT auth middleware** — *Phase 1, now confirmed required*; endpoints stop taking
  `?email=` and derive the user from the JWT (also closes the `/sync/preview` no-auth issue).
- **Event/todo persistence + list API** — *Phase 1*; the app reads structured items from here
  (raw bodies never stored, D5).
- **`POST /api/v1/devices/register` + FCM sender service** — *new*, for reminders.
- API stays REST/JSON; the backend remains the only holder of Gmail tokens (D4).

## Tooling / repo

- `frontend/` holds the Flutter app (polyglot monorepo with the Python `backend/`).
- Add Flutter ignores to `.gitignore` at scaffold time: `frontend/build/`, `frontend/.dart_tool/`,
  `frontend/.flutter-plugins`, `frontend/.flutter-plugins-dependencies`, `frontend/ios/Pods/`,
  `frontend/**/GoogleService-Info.plist`, `frontend/**/google-services.json` (Firebase configs:
  treat as secrets, do not commit).
- Firebase project for FCM: document setup in an `infra/`-adjacent note; no secrets committed.

## Testing

- Flutter `unit`/`widget` tests for `auth`, `api_client`, and `ads` isolation.
- Backend tests for the new OAuth-exchange and `devices/register` endpoints.
- A firewall-guard test: a Dart file under `ads/` referencing `event`/`child` data is BLOCKed.

## Accepted trade-offs

- **FCM setup** (APNs key in Firebase, FCM sender on backend) is more work than a managed push
  service would have been — accepted for a single mature cross-platform path.
- **Flutter Web** (the "web later" path) is a heavy, app-style build with weak SEO — fine as a
  logged-in web app later, not a marketing site.

## Out of scope (separate later brainstorm)

- Screen-by-screen UI / feature design (calendar view, todo interactions, onboarding, sync UX) —
  likely with visual mockups.
- Paid ad-free tier purchase flow (Stripe / store IAP) — Phase 2.
- Flutter Web build hardening.

## Open items to settle in planning

- Firebase project creation + APNs key (manual, Google console).
- Apple Developer + Google Play accounts for store submission (later, not needed to build/run).
- Exact package versions pinned during the implementation plan.
