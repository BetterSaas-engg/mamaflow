# E0 — Google OAuth verification (restricted scope): the checklist

Mamaflow requests `gmail.readonly` — a **restricted** scope. Leaving Testing mode (no 100-tester
cap, no "unverified app" interstitial) requires Google's restricted-scope verification, which
includes an **annual CASA security assessment**. Typical end-to-end timeline is **6–12 weeks** —
this is the launch long-pole, so it runs in parallel with everything else. Ads (Track E) are
gated behind it (D19/D21: "ships and verifies").

## Hard prerequisite: a domain we own

Google requires the app's **homepage and privacy policy on a domain you own**, verified via
Search Console. `mamaflow-production.up.railway.app` cannot be used (Railway owns it).

- [ ] **1. Acquire the domain** (e.g. `mamaflow.app` / `getmamaflow.com` — PM pick).
- [ ] **2. Verify it in Search Console** (DNS TXT record) with the same Google account that owns
      the OAuth project.
- [ ] **3. Host two pages on it** (a static one-pager is enough to start; Railway custom domain,
      GitHub Pages, or Vercel all work):
      - **Homepage** — what Mamaflow does, who it's for, visible link to the privacy policy.
        Must describe the Gmail data use ("reads your inbox to extract family events…").
      - **Privacy policy** — publish `docs/privacy-policy.md` (already drafted, includes the
        Firebase/FCM sub-processor row). Must name the Gmail data accessed, purpose, storage,
        deletion path (Settings → Delete account), and the **Limited Use disclosure** verbatim:
        "Mamaflow's use and transfer of information received from Google APIs adheres to the
        Google API Services User Data Policy, including the Limited Use requirements."

## Console work (after the domain)

- [ ] **4. OAuth consent screen** (project `Mamaflow`): app name, logo (120x120), support email,
      **authorized domain** = the new domain, homepage + privacy-policy URLs, developer contact.
- [ ] **5. Scope justification** (written in the verification form): why `gmail.readonly` is
      needed (metadata-first scan → blocklist → extract family events server-side; narrower
      scopes like `gmail.metadata` don't expose message bodies needed for extraction).
- [ ] **6. Demo video** (unlisted YouTube): the full OAuth flow from the app, the consent screen
      showing the scope, then the feature the scope powers (sync → agenda items). Must show the
      app name matching the consent screen.
- [ ] **7. Submit for verification** → brand verification first (days), then restricted-scope
      review; Google replies by email, expect back-and-forth.

## CASA (Cloud Application Security Assessment)

- [ ] **8. CASA Tier 2** — required for restricted Gmail scopes, annual. Options: an authorized
      lab (paid, ~$500–$4.5k) or the self-scan route where eligible. Scope: the deployed backend.
      Our posture is already strong (JWT auth, soft-delete, env-only credentials, types-only
      logging, injection wrap, deterministic firewall) — the audits in HANDOFF are the evidence
      trail to hand the assessor.

## Ordering / what can start today

1. Domain purchase (5 min, PM) → unblocks everything else.
2. Homepage + privacy-policy hosting (Claude can build the static pages once the domain exists).
3. Consent-screen fields + scope justification + video script (Claude drafts; PM records).
4. Submit; CASA runs during/after Google's review.

Keep testing under the 100-user cap meanwhile — verification is not needed for TestFlight/
Firebase-App-Distribution testers who are on the Test users list.
