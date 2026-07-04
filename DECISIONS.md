# DECISIONS.md — Mamaflow decision log

> Canonical, append-only log of architectural & product decisions. `AGENTS.md` and `CLAUDE.md` defer
> here for the "why." When you make a decision, append it as the next `Dn` with its rationale.
> **Status:** `locked` (do not re-litigate) · `under review` (being reconsidered) · `deferred`
> (decided, not built yet).

| # | Decision | Status | Notes / why |
|---|----------|--------|-------------|
| D1 | Gmail OAuth first, Yahoo second | locked | Gmail is the dominant inbox for the target user; one provider to prove the pipeline. |
| D2 | Shim/broker split — the shim is public and never holds credentials; the private broker holds tokens + runs the privacy pipeline | deferred | Deployment-topology concern, premature for Phase 0 (currently a single FastAPI app). Build at production. |
| D3 | Wrap-by-default prompt-injection defense | locked | Every email body is wrapped in randomized nonce-tagged boundaries before Claude sees it; body text is data, never instructions. |
| D4 | OAuth tokens never in the database | locked | In-memory for Phase 0; Secret Manager references in prod. Never in DB, env files, or source. |
| D5 | Raw email body never stored | locked | Only structured extractions persist; bodies are processed in-memory. |
| D9 | Frontend = Flutter (mobile-first; web later via Flutter Web) | locked | Chosen over PWA+Capacitor / React Native+Expo because push is core at launch and the team is productive in Flutter; AdMob is first-class. See docs/superpowers/specs/2026-06-22-frontend-platform-flutter-design.md. |
| D13 | Sender blocklist is structural, not a user setting | locked | Managed via DB seed + admin; allowlist takes precedence over blocklist. |
| D14 | Microsoft Presidio for PII redaction (Layer 2) | locked | Custom recognizers for account numbers, US SSN (context-boosted), Canadian SIN. |
| D19 | **THE FIREWALL** — no user content (email/health/photos, or any summary, keyword, or inference derived from them) may EVER reach the ad system | locked | Ads may target ONLY non-content signals: coarse geo, app screen/context, user-typed profile fields not derived from content, and Google's own ad-profile data. The ad SDK is frontend-only and structurally isolated from event/child components; no server-side ad-targeting parameter is built from content. `ad_profile_builder` / `deals_matcher` / `deals_builder` are KILLED. Enforced deterministically by `scripts/firewall-guard.sh`. Rationale: Gmail is a Limited-Use scope — using content (or derivations) for ads fails OAuth verification and destroys the privacy wedge. |
| D20 | Native app distribution (App Store + Play Store) | locked | Supersedes the original "PWA only — no App Store" stance; reliable push requires a native app. |
| D21 | Monetization: free + firewalled ads PLUS a paid ad-free tier (Cozi model) | locked | Launch ads = in-house/static and/or AdMob non-personalized (`npa=1`). Personalized AdMob deferred. Ads stay firewalled per D19. |
| D22 | Push notifications via Firebase Cloud Messaging (FCM) for both platforms | locked | iOS via an APNs key in Firebase. Backend sends with the FCM HTTP v1 API. |
| D23 | Mobile auth = Google sign-in serverAuthCode → backend token exchange | locked | Gmail tokens stay server-side (D4); app holds only its session JWT. |
| D24 | Extracted items persist in a SINGLE `items` table (events + actions via `item_type`) | locked | Matches the unified FamilyItem schema; simplest `GET /items` query. Single table over split events/actions. (Phase B) |
| D25 | Item todo status = `open`/`done`/`dismissed` (MVP); snooze deferred | locked | Keeps `PATCH /items/{id}` MVP-small; snooze lands later with the reminder scheduler. |
| D26 | Reminder scheduling via in-process **APScheduler** (when the FCM sender is built) | deferred | Simplest for a single Railway instance; revisit a task queue at scale. The sender itself is deferred (D27). |
| D27 | Device-registration endpoint built now; **FCM push sender + scheduler deferred** until a Firebase service account + APNs key exist | deferred | Unblocks the app's token registration without blocking on push infra/accounts. |
| D28 | Mobile sign-in = direct **OAuth2 authorization-code + PKCE** (flutter_web_auth_2), not google_sign_in's serverAuthCode | locked | google_sign_in 7.x on iOS only mints a serverAuthCode at initial sign-in and `addScopes` nulls it, so a Gmail-scoped code is unobtainable (verified in plugin source; failed on simulator AND device). The app now runs Google's consent directly (PKCE S256, `access_type=offline`, iOS client, redirect_uri derived server-side) and posts `{code, code_verifier}` to the backend, which exchanges without a client secret. D23's principle is unchanged: Gmail tokens server-side, app holds only its JWT. Verified end-to-end on a physical iPhone 2026-07-02. |
| D29 | Extraction model stays **`claude-sonnet-4-6`** (strict tool-use output) | locked | Reviewed 2026-07-04 vs Sonnet 5 (~30% more tokens via new tokenizer, slightly higher real cost) and Haiku 4.5 (3–5x cheaper, quality unproven on messy school emails). Proven on the real inbox; revisit at volume — a Haiku cost-eval is the natural next test since strict tool-use now guarantees schema validity on any model. |

*(D6–D8, D10–D12, D15–D18 are unallocated in the original log; add them here if/when they surface.)*

## Frontend platform — resolved

Resolved 2026-06-22: **Flutter** (mobile-first; web later). Rationale and foundation in
`docs/superpowers/specs/2026-06-22-frontend-platform-flutter-design.md`; see D9, D22, D23. The driver
was that push/reminders are core at launch and a PWA can't deliver reliable iOS push (only for
"Add to Home Screen" installs); the team's Flutter experience made it the best-value choice.
