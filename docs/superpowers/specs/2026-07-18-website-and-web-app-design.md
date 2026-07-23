# Website + desktop web app — design

**Date:** 2026-07-18
**Status:** approved (brainstorm 2026-07-18)
**Scope decision:** both pieces, landing first. Static HTML landing site; Flutter Web app at
full mobile parity minus push and ads; auth approach A (same app JWT, web OAuth client).

## Why now

- E0 (Google OAuth verification) requires a hosted privacy policy on our domain; the ad launch
  requires `app-ads.txt` there. A website is on the critical path regardless of desktop login.
- Users should be able to sign in from a desktop/laptop browser and use the same
  agenda/calendar the phone has (D9 locked: "web later via Flutter Web" — this is that phase).
- No domain exists yet. Nothing here blocks on it: both sites deploy to free `*.vercel.app`
  URLs; the real domain is a config swap at the end (DNS + OAuth console + `app-ads.txt`).

## Overall shape

| Piece | Tech | Host | URL (until domain) |
|-------|------|------|--------------------|
| Landing site | static HTML/CSS, no JS/trackers | Vercel project rooted at `website/` | `mamaflow.vercel.app` (or similar) |
| Web app | Flutter Web build of `frontend/` | second Vercel project (static output) | `mamaflow-app.vercel.app` |
| API | existing FastAPI on Railway | unchanged | `mamaflow-production.up.railway.app` |

After the domain: apex/`www` → landing, `app.` subdomain → web app. API stays on Railway.

## 1. Landing site (`website/` at repo root)

Three hand-written pages, Mama Coral branded (colors/fonts per D33; logo PNGs come from the
existing `AppLogo` master generator — nothing drifts):

- `index.html` — hero (logo + wordmark), value proposition, the trust/privacy lines already
  used on the sign-in screen, store badges (placeholders until the apps are published), link
  to the web app.
- `privacy.html` — the privacy policy's permanent home (E0 prerequisite). Content moves from
  the current in-repo policy doc; that doc becomes a pointer to this page.
- `app-ads.txt` — added at ad launch (needs the real domain + AdMob publisher id), not now.

Constraints: zero JavaScript, zero analytics/trackers — instant load, and the site itself
demonstrates the privacy positioning. Any future analytics needs its own decision.

## 2. Web app — frontend (Flutter Web)

- Scaffold the web target (`flutter create --platforms web .`); brand the web `index.html`
  shell + loading splash to match the native splash (coral + logo).
- **Auth:** a `kIsWeb` branch at the existing plugin boundary (`lib/auth/google_auth_codes.dart`)
  runs OAuth 2.0 auth-code + PKCE against a **new web OAuth client** with an https redirect
  back to the app's own origin, then posts `{code, code_verifier}` to the new web endpoint
  (below). New dart-define: `GOOGLE_WEB_CLIENT_ID`. Mobile flow (D28) is untouched.
- **Session storage:** same `flutter_secure_storage` interface (its web implementation —
  WebCrypto-encrypted local storage). Accepted as weaker than the phone's secure enclave;
  mitigated by the shorter web TTL (below).
- **Layout:** reuse the existing screens inside a centered max-width (~720 px) shell.
  Desktop-optimized layouts (two-pane, keyboard shortcuts) are a later polish pass, not MVP.
- **Push:** `PushService` no-ops on web (`kIsWeb` guard). Reminders keep arriving on the phone.
- **Ads:** none on web. `google_mobile_ads` does not compile for the web target, so `lib/ads/`
  gets a conditional-import stub; the bidirectional ad-isolation test and firewall guard keep
  applying unchanged (D19).

## 3. Web app — backend additions

- **`POST /api/v1/auth/google/web`** — same contract shape as `/auth/google/mobile`
  (`{code, code_verifier}` → `{access_token, expires_in, user}`), but:
  - exchanges with the **existing web OAuth client** (`GOOGLE_CLIENT_ID` +
    `GOOGLE_CLIENT_SECRET` — already a web client, used by the legacy dev flow; no new backend
    env for it). The app-origin redirect URI is added to that client in the Google console.
    The frontend's `GOOGLE_WEB_CLIENT_ID` dart-define carries the same client id value,
  - `redirect_uri` is server-derived from the configured app origin, never client-supplied
    (same defense-in-depth as `mobile_redirect_uri`),
  - identity from the verified `id_token`, Gmail tokens stored server-side via the existing
    `store_token` path — D4/D23 principles unchanged.
- **CORS middleware** (Starlette `CORSMiddleware`) allowing only the configured app origin(s);
  env `WEB_APP_ORIGINS` (comma-separated; empty = middleware not added, today's behavior).
- **Web session TTL:** `WEB_TOKEN_EXPIRE_MINUTES` default 10080 (7 days) vs mobile's 30 days
  (D31) — browser storage is more exposed than a device keychain. Gets a decision-log entry.
- All blocking Google calls off the event loop (`asyncio.to_thread`), matching the 2026-07-18
  audit conventions; types-only logging throughout.

## 4. Data flow, errors, testing

- Same REST/JSON contract as mobile; 401 → existing auto-sign-out flow; sync progress polling
  unchanged. No new content flows; the firewall surface is untouched.
- Backend: TDD per project convention; new tests for the web endpoint (happy path, bad code →
  400 sanitized, redirect derivation, TTL claim) and CORS behavior. Security-auditor pass
  required (touches token flows).
- Frontend: existing widget tests keep passing (web branch behind the already-testable
  `google_auth_codes` boundary); `flutter analyze` clean.
- **CI:** add a `flutter build web` step to the existing CI workflow so web-compile breakage
  (e.g. a stray `dart:io` or the ads import) can never land silently.

## 5. Build order

1. **W1 — landing site:** `website/` pages + Vercel deploy to a `vercel.app` URL. No domain,
   no backend change. Ships this week if desired.
2. **W2 — backend web auth:** endpoint + CORS + TTL knob (TDD, audited). Testable with curl
   before any frontend exists.
3. **W3 — Flutter web target:** scaffold, `kIsWeb` auth branch, ads stub, push guard,
   constrained layout; verified against localhost + Railway.
4. **W4 — deploy + CI:** Vercel app project, `flutter build web` in CI.
5. **Domain arrival (user checklist, ~30 min):** buy domain → Vercel domain attach (both
   projects) → Google console: add web-client redirect URIs for the real origin → update
   `WEB_APP_ORIGINS` on Railway → `app-ads.txt` at ad launch.

## Out of scope

Web push (FCM-for-web/service worker), ads on web, blog/SEO beyond the landing page,
desktop-optimized layouts, paid tier/Stripe (Track E), analytics of any kind.
