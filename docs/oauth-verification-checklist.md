# E0 — Google OAuth verification checklist (restricted scope: gmail.readonly)

_Why: the app cannot leave "Testing" mode (100-user cap, unverified-app warnings) until
Google verifies it for the restricted Gmail scope. This is also the gate for the ad layer
(D21: only after the engine "ships and verifies"). Lead time: expect **4–8+ weeks** —
brand verification, scope review, and an annual **CASA Tier 2 security assessment**._

## Prerequisites (have before submitting)

- [ ] **Public homepage** describing Mamaflow, on a domain you own (verification requires
      domain ownership via Search Console; a bare railway.app URL is usually not accepted
      for branding — buy/point `mamaflow.app` or similar, can be a simple landing page).
- [ ] **Privacy policy** published at that domain — draft ready: `docs/privacy-policy.md`
      (fill placeholders: contact email, retention window; PM review).
- [ ] **In-app consent matches**: OAuth consent screen app name/logo/links = the homepage
      branding (mismatches are the #1 rejection cause).
- [ ] **Demo video** (YouTube, unlisted OK): shows the full OAuth flow from the app — the
      consent screen with the scope, then how Gmail data is used in-app (sync → items).
- [ ] **Scope justification text**: why gmail.readonly is essential (extract family events
      from email; read-only; metadata-first; no narrower scope exists that works).

## Talking points our architecture already earns (use in the justification)

- Read-only scope; **metadata-first fetch** — blocked senders' bodies never retrieved.
- **Raw bodies never stored**; only structured events persist (D5).
- PII redaction (Presidio) before any third-party processing.
- Tokens server-side only, Secret Manager (D4); never on device or in the app DB.
- **Content firewalled from ads** — enforced by CI guard, not policy (D19).
- Soft-delete + user-initiated disconnect/deletion.

## Process

1. Console → OAuth consent screen → **Publish app** → triggers verification flow.
2. Submit branding + scopes + justification + demo video; respond to Trust & Safety emails
   (they iterate — reply fast, same thread).
3. **CASA Tier 2**: Google will direct you to an authorized lab (or self-scan option for
   Tier 2) — plan for a scan of the deployed backend + remediation round.
4. Annual recertification thereafter.

## Blockers to clear first (tracked in HANDOFF)

- Domain + landing page (user).
- Contact email for privacy policy (user).
- Backend already deployed (done — Railway). Keep single-instance until cache-coherency fix.

_Ads (Track E) stay blocked until this completes. Start early; iterate while building._
