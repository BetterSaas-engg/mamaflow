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
| D9 | Frontend delivery: PWA only — no native wrapper | **under review** | Reopened: iOS web-push only fires for "Add to Home Screen" installs — weak for a reminders product. Evaluate PWA+Capacitor vs React Native/Expo vs Flutter before building the frontend. See **Open: frontend platform** below. |
| D13 | Sender blocklist is structural, not a user setting | locked | Managed via DB seed + admin; allowlist takes precedence over blocklist. |
| D14 | Microsoft Presidio for PII redaction (Layer 2) | locked | Custom recognizers for account numbers, US SSN (context-boosted), Canadian SIN. |
| D19 | **THE FIREWALL** — no user content (email/health/photos, or any summary, keyword, or inference derived from them) may EVER reach the ad system | locked | Ads may target ONLY non-content signals: coarse geo, app screen/context, user-typed profile fields not derived from content, and Google's own ad-profile data. The ad SDK is frontend-only and structurally isolated from event/child components; no server-side ad-targeting parameter is built from content. `ad_profile_builder` / `deals_matcher` / `deals_builder` are KILLED. Enforced deterministically by `scripts/firewall-guard.sh`. Rationale: Gmail is a Limited-Use scope — using content (or derivations) for ads fails OAuth verification and destroys the privacy wedge. |
| D20 | PWA only — no App Store | **under review** | Tied to D9; same re-evaluation. |
| D21 | Monetization: free + firewalled ads PLUS a paid ad-free tier (Cozi model) | locked | Launch ads = in-house/static and/or AdMob non-personalized (`npa=1`). Personalized AdMob deferred. Ads stay firewalled per D19. |

*(D6–D8, D10–D12, D15–D18 are unallocated in the original log; add them here if/when they surface.)*

## Open: frontend platform (D9 / D20 under review)

Must be decided before building `frontend/`. **Driver:** iOS Safari delivers web push ONLY to PWAs
the user has "Added to Home Screen" (low conversion, hidden flow) — and reminders/notifications are
core to the product. The `frontend/` folder name is deliberately platform-agnostic so this stays open.

Options to evaluate (ranked by fit to the current Python + React/JS stack):
1. **PWA + Capacitor wrapper** — keep the React/Vite codebase; wrap to native for real push
   (APNs/FCM) + store presence when needed. Lowest rewrite; best stack fit.
2. **React Native / Expo** — more native, reuses React skills, real native push; adds an app-store
   build pipeline + RN-specific UI code (not direct web reuse).
3. **Flutter** — best UI/perf, but Dart is a new language (no reuse with React/JS); biggest pivot.

Resolve via a brainstorm; record the outcome as a new decision and flip D9/D20 to `locked`.
