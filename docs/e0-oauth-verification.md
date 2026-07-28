# E0 — Google OAuth verification (restricted scope): the checklist

Mamaflow requests `gmail.readonly` — a **restricted** scope. Leaving Testing mode requires Google's
restricted-scope verification, which includes an **annual CASA security assessment**. This is the
launch long-pole and it gates ads (D19/D21: "ships and verifies").

> **Revised 2026-07-28** against primary Google / App Defense Alliance sources. The July 15 draft was
> directionally right but missed two things that change the plan: the **7-day refresh-token expiry**
> in Testing mode, and the **required in-app pre-consent disclosure** we don't have. Current cost and
> timeline: **~$675–855 up front and again annually, 6 weeks best case / 2–3 months realistic.**

Applies only to `provider=google` users. IMAP users (Yahoo/Rogers/iCloud, D38) are entirely off this
track — a bigger win than it looked when we chose it.

## Why this is urgent, not "later"

| | Testing (today) | Published, unverified | Published, verified |
|---|---|---|---|
| Audience | 100 test users | anyone, but **100 new users for the project's LIFETIME** | unlimited |
| Refresh tokens | **expire 7 days after consent** | normal | normal |
| Warning screen | yes | yes | no |

- **Google testers must re-consent every 7 days.** `access_type=offline` does not save us — the
  refresh token itself dies. If a Google tester says the app "went quiet" after about a week, this is
  why, not a bug in our sync. (Correction to the July 15 note that testers were unaffected: they are
  on the Test users list, but the 7-day tax still applies.)
- **The 100-user unverified cap is a lifetime counter and cannot be reset.** Publishing early to
  dodge the 7-day expiry would burn it permanently. Stay in Testing until verified.

No small-scale exemption avoids both — the "personal use / under 100 users" carve-out is functionally
Testing mode with the same tax.

## What we already satisfy ✅

- Homepage on our own domain (**themamaflow.com**), describing the product, not login-gated.
- Privacy policy **on the same domain** (a hard requirement), linked from the homepage.
- Explicit **Limited Use** statement naming the Google API Services User Data Policy.
- **Anthropic named as a sub-processor**, with what is sent and why.
- Retention/deletion documented; account deletion implemented.
- **The ad firewall (D19) is verbatim Google's own criterion** — Limited Use bans using Google user
  data for ads, retargeting, or transfer to ad platforms/data brokers. Lead with it in the scope
  justification; it is an asset in review, not merely a constraint we accept.

## What is missing ❌

- [ ] **1. In-app pre-consent disclosure screen — required, and absent.** The Workspace user data
      policy (updated 2026-07-13) requires a prominent in-app disclosure that *immediately precedes*
      the OAuth request, requires **affirmative action** (a tap — navigating away must not count),
      does not auto-dismiss, and **cannot live only in the privacy policy**. It must state what is
      accessed, how it's used, how it's shared, plus the Limited Use adherence statement. This is a
      Flutter change and the most commonly missed requirement. Wording needs PM sign-off.
- [ ] **2. Domain verification in Search Console** — as a **Domain (DNS)** property, using an account
      that is an **Owner/Editor of the GCP project**. A mismatch here fails silently.
- [ ] **3. Consent-screen fields** — app name (must match the homepage), logo, support email,
      authorized domains, homepage + privacy-policy URLs, developer contact.
- [ ] **4. Scope justification** — must argue why a narrower scope will not do. "Improves user
      experience" is auto-rejected. Ours: `gmail.metadata` exposes headers only, while event details
      (dates, times, locations) live in the body and the `text/calendar` part — D37 is the receipt: a
      real invite whose date existed *only* in the ICS part.
- [ ] **5. Demo video** — YouTube **unlisted** (not Drive), in **English** including the consent
      screen's own language toggle, showing the full consent flow, the correct app name, **the OAuth
      client ID legible in the address bar**, and each scope's use. Record it *after* revoking our own
      prior grant, or the consent screen never appears — a common rejection. No stated length limit.
- [ ] **6. Freeze branding before submitting.** Any later change to app name, logo, redirect URI,
      homepage, privacy-policy URL, or scopes **resets verification**.
- [ ] **7. Submit** brand verification (2–3 days) → scope verification (~6 weeks quoted).

## CASA

Required — no way around it. Google's rule: if you store or transmit restricted-scope data on
servers, you need the assessment. Our FastAPI/Railway backend qualifies ("third party" is written
from Google's perspective — we are the third party). Narrowing scope doesn't help: **all four** Gmail
scopes (`readonly`, `metadata`, `modify`, `mail.google.com`) are restricted. Claims that
`gmail.metadata` avoids CASA are false.

- [ ] **8.** Expect **Tier 2 / AL1** — we run the scan, a lab reviews the evidence; the lab does not
      touch our app or code. We don't choose the level; Google assigns it risk-based.
- **We cannot start it.** Google triggers it by email *after* brand + scope verification pass. Known
  2026 failure mode: that email never arrives — escalate on the existing verification thread rather
  than resubmitting.
- **30-day deadline** to submit once initiated.
- Only **9 authorized assessors** exist; "CASA" sold by anyone else yields no valid Letter of
  Validation. TAC Security publishes **$675 (Basic) / $855 (Premium)**, 1–3 weeks; Leviathan
  $3,000–4,500. Get a written quote — TAC's own pages contradict each other.
- **Renews annually** — recurring cost, not one-off.
- The $15k–$75k figures still circulating in blog posts describe the pre-CASA regime. Ignore them.
- Pre-scan the backend against **OWASP ASVS 4.0** before the lab step; it collapses that step from
  weeks to days. Our posture is already strong (JWT auth, soft-delete, secrets outside the DB,
  types-only logging, injection wrap, deterministic firewall) and the HANDOFF audit trail is the
  evidence to hand over.

**The Anthropic dependency is the highest-risk item in our stack.** Third-party transfers are
permitted when necessary for a *prominent user-facing feature* — extraction-to-calendar is exactly
that, and Presidio redaction strengthens it. Three hard constraints:

1. **Training on the data is banned outright.** We must be able to state Anthropic does not train on
   API inputs — keep a dated copy of the commercial terms as evidence.
2. Anthropic is our contractor, so we are responsible for its compliance with Google's policy.
3. It must be disclosed by name in the privacy policy (done).

## Common rejection reasons

1. Generic scope justification (the #1 cause).
2. Requesting scopes for features not yet implemented — "future enhancements" is explicitly rejected.
3. Consent-screen scopes ≠ submitted scopes.
4. Demo video missing the client ID, non-English consent screen, or no visible consent flow.
5. Privacy policy on a different domain, unlinked, or describing the wrong behaviour.
6. App name mismatch between consent screen and homepage.
7. Occasionally a reviewer false-positive on the homepage requirement — push back before redesigning.

## Ordering

1. Search Console domain verification (PM, minutes).
2. In-app disclosure screen (Claude builds; PM approves wording).
3. Freeze branding → submit brand → submit scope verification.
4. Record demo video.
5. Wait for Google's CASA email → engage an assessor from the authorized nine.

**Do not burn the 100-user unverified cap on beta.** Keep beta in Testing mode and accept the weekly
re-auth for Google testers — or lean on IMAP onboarding, which avoids the 7-day re-consent entirely.
