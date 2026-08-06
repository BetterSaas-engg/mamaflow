# Billing — research and recommendation (Aug 2026)

Researched against primary sources (Apple Review Guidelines, Play policy pages, court filings, Stripe
/ RevenueCat docs). **Not yet a decision** — the pricing call is the PM's, and it is the part that
actually matters. Sources are cited inline; anything unverified is marked.

---

## The finding that reframes the question

The billing rail is **second-order**. The price and the marginal cost are first-order.

Our measured extraction cost is **~$2.82 USD/user/month** (D39, after the retry fix). Against a
hypothetical $4/month subscription:

| Rail | Net of fees | Gross margin over $2.82 |
|---|---|---|
| Apple IAP, Small Business Program (15%) | $3.40 | **$0.58** |
| Play Billing (15%) | $3.40 | **$0.58** |
| Own Stripe checkout (US card, USD) | $3.44 | **$0.62** |

Moving from Apple's IAP to our own Stripe checkout is worth **about 4¢ per user per month** at that
price. The $0.30 fixed fee plus the unavoidable 2% currency conversion (see below) eats essentially
the whole 15% saving. Picking the perfect rail roughly doubles a margin that is bad either way.

**So: fix the price first. Then take the simplest legal rail.**

> Note: $4/$7 are illustrative figures used for modelling, not prices anyone has set.

### Family is structurally mispriced relative to Pro

Straight from `services/entitlements.py`:

| Tier | Mailboxes billed to us | Relative cost to serve |
|---|---|---|
| Free | 1 | 1× |
| Pro | 2 | 2× |
| **Family** | 2 per member × 2 members = **4** | **4×** |

Family costs roughly **twice what Pro costs** to serve. Any price where Family < 2× Pro gives Family
*worse* unit economics than Pro — the opposite of what a premium tier should do. Either price Family
at ~2× Pro, or cap Family at 3 mailboxes total.

Annual billing is the highest-leverage lever available: same 15% store fee, but on Stripe it drops
the effective rate from ~13% to ~6%, and it cuts involuntary-churn *events* twelvefold.

---

## What we are actually allowed to do

**In-app purchase is mandatory on both stores for our product.** There is no version of this where we
skip it.

- Apple **3.1.1** — unlocking features in-app must use IAP. **3.1.3(b)** lets us honour a
  web-purchased subscription inside the app *only if the same thing is "also available as in-app
  purchases."* The reader exception (3.1.3(a)) covers magazines/books/music/video — not us.
- Google's Payments policy names our case twice: content **subscription services**, and *"an ad-free
  version of an app."*

**Canada gets no relief on either store.**

| | Canada storefront | US storefront |
|---|---|---|
| Must offer IAP | Yes | Yes |
| May sell on our own web app | Yes (and honour it in-app) | Yes |
| May link out / show external prices in-app | **No** | **Yes**, currently at 0% commission |

Storefront means the *user's* account country, not our incorporation — so any link-out has to be
gated at runtime on `Storefront.current.countryCode`, not by build flag. Google's cheaper US fee
structure doesn't reach Canada until **30 Sep 2027**.

**The US 0% link-out is a litigation artifact and is not safe to build on.** The Ninth Circuit
affirmed the contempt finding in Dec 2025 but **vacated** the total commission ban; the Supreme Court
granted certiorari in Jun 2026 and the rate-setting is stayed. Apple's published fallback is
**27% / 12%**, which would make a link-out *worse* than IAP overnight.

---

## Recommendation

### 1. Re-price before writing any billing code
Zero code risk, highest leverage. Price Family at ~2× Pro (or cap its mailboxes), and push annual.

### 2. Native IAP on both stores, via RevenueCat
- It is the only rail legal on **every** storefront we serve, and roughly half our users are Canadian
  where there is no relief at all.
- 3.1.3(b) means we must offer IAP regardless of what else we do.
- **Do not build Android link-out or alternative billing.** Modelled at $4, $7 and annual, Play
  Billing at 15% beats alternative billing (10% Google + ~5.7% Stripe) at *every* price point — plus
  mandatory enrolment, 24-hour transaction reporting, and per-install download fees from Oct 2026.
- RevenueCat is **free to $2,500/month** tracked revenue, then 1% of gross. It removes the entire
  store-notification state machine (below), which for a two-person team is not a close call.

### 3. Keep the entitlement architecture exactly as it is
`entitlements_for()` failing closed to free on an unknown tier is precisely right for billing: a
store outage or an out-of-order webhook must never 500 a parent out of their calendar. Add a
`subscriptions` table keyed on Apple `originalTransactionId` / Google `purchaseToken`, plus
`processed_store_events(event_id PK)` for idempotency, and make `users.tier` a **derived projection**
rather than something a webhook writes directly. Keys go in Secret Manager (D4), never the DB.

**Firewall note (D19):** subscription state, tier and churn signals must never reach the ad layer as
targeting parameters.

### 4. Sell on the web app via Stripe — for the web app
3.1.3(b)-clean, no entitlement needed, works in Canada, and it's where annual conversions will
happen. Just don't advertise it inside the mobile apps outside the US.

⚠️ Two Canadian Stripe constraints: a Canadian account **cannot settle USD** (so every USD charge
pays the 2% conversion, permanently), and **Stripe subscriptions are unavailable to customers in
Quebec** — a real problem for a Canadian consumer product going web-only.

### 5. Do NOT enable Apple Family Sharing
It is **irreversible once enabled**, gives 5 seats where we intend 2, has **no Google equivalent**
(so iOS families would get 5 seats and Android families 2 for the same price), and breaks
`appAccountToken` identity binding. Our own households model (D46) already does this better,
cross-platform, and on web. One IAP bought by the household owner; entitlement fanned out by
`visible_user_ids()`.

---

## The store-notification failure modes (what RevenueCat buys us)

Kept here because if we ever drop RevenueCat, these are the bugs waiting:

1. **Revoking on "cancelled."** Google's state is literally `CANCELED` = *cancelled but not expired*.
   Apple's `AUTO_RENEW_DISABLED` means "won't renew", not "access ends". The most common
   revenue-losing bug. Entitlement should be `ACTIVE ∪ GRACE ∪ (CANCELED while expiry > now)`.
2. **Grace ≠ retry.** Apple's grace period is opt-in (3/16/28 days); billing retry runs up to 60 days
   with the user *unentitled*, then a renewal arrives weeks later and must re-grant.
3. **Google's 3-day acknowledgement** — miss it and the purchase is auto-refunded and entitlement
   revoked. It also blocks all plan changes while pending.
4. **Out-of-order and duplicate delivery.** Pub/Sub is at-least-once and unordered. Dedupe on the
   message id; guard with a monotonic `last_applied_at`.
5. **Sandbox contamination.** Gate on Apple's `environment` and Google's `testPurchase` *before*
   writing a tier.
6. **Identity binding.** Apple's `appAccountToken` is absent for offer-code, promoted and
   family-shared purchases — key on `originalTransactionId`. Google's `obfuscatedAccountId` is capped
   at 64 chars and forbids PII, so mint an opaque UUID; do not hash the email.
7. **Google `linkedPurchaseToken`** — on upgrade/downgrade a new token arrives and the old one must be
   revoked, or it's a live subscription-sharing exploit.
8. **Refunds.** Apple has `REFUND_REVERSED` (usually unimplemented) and partial refunds via
   `revocationPercentage`; consumption requests must be answered within 12 hours. Google's voided-
   purchase lookback is a hard 30 days.
9. **Payload shape.** Apple's V2 notification has four mutually exclusive bodies; a parser assuming
   `data` crashes on `RESCIND_CONSENT`. Parse defensively — the D34 coerce-don't-reject stance.

---

## Consumer law — a second, independent reason to prefer IAP

Researched separately against primary sources. The short version: **IAP-only removes the hardest half
of the compliance surface**, because the platform provides the cancellation UI, the refund mechanics
and the chargeback exposure. Running our own checkout means owning all of it.

**Dated obligation, five weeks out.** Quebec's **Bill 10 (2026, c. 16) is in force 12 September
2026** and requires an *"accessible et facilement repérable"* in-product unsubscribe button for any
subscription concluded over the internet, plus written notice before a promotional price steps up.
This bites **only if we take Quebec customers' money through our own checkout** — an IAP subscription
is cancelled in Apple/Google's own UI. (Recall Stripe subscriptions are unavailable to Quebec
customers anyway, so web-only was never viable there.)

**California's ARL is the practical floor and it applies to us.** In force since **1 July 2025**, it
reaches "any business that makes an automatic renewal offer to a consumer in this state" — an Ontario
company selling to a Californian is covered. It requires affirmative consent, **cancellation
exclusively online in the same medium used to sign up**, and an **annual reminder**. Build to
California and we clear ROSCA, New York (Nov 2025) and Colorado (Feb 2026) in one pass.

**The FTC's "click to cancel" rule was vacated in full** (8th Cir., 8 Jul 2025, on procedural
grounds — the FTC skipped a required regulatory analysis). The FTC is back at the ANPRM stage as of
Mar 2026, so a replacement is realistically 18–36 months out. **Do not build to it** — but note its
substance was essentially California's, so building to California future-proofs us anyway. What still
binds today is **ROSCA**: clear disclosure before billing information is taken, express informed
consent, and *"simple mechanisms to stop recurring charges."*

**Ontario: the live rule is the old Act, not the new one.** The Consumer Protection Act **2023 is not
in force** (confirmed: the 2002 Act's repeal note is still unexecuted on a consolidation current to
3 Aug 2026, and its auto-renewal section is an empty shell pending regulations that were never made).
What governs today is **O. Reg. 17/05 s.42**: any price or term change needs **30–90 days' advance
notice**, a free and accessible way to respond, and a real option to cancel or keep the old terms —
and **a non-compliant notice is simply ineffective**. That applies to us now.

**French is not optional if we sell to Quebec.** Quebec CPA s.26 and Charter s.55 require the
subscription contract and related documents to exist in French and to be **presented before** the
English version. Charter **s.52.1** is conditional but sharp: the moment a French build of the app
exists anywhere, it must be available in Quebec **on no-less-favourable terms**. Charter s.52 catches
marketing pages ("regardless of the medium used").

**Drip pricing (Competition Act s.52(1.3) / s.74.01(1.1)):** the advertised price must be attainable.
Government taxes are carved out, so GST/HST need not be in the headline — but any *mandatory*
non-tax fee must be. Advertising "$5.99/month" while charging a mandatory processing fee on top is a
per se false representation.

**What IAP does NOT offload:** the pre-purchase disclosure and affirmative-consent screen (that is our
paywall, and Apple's Guideline 3.1.2(c) puts it explicitly on us), the annual reminder, statutory
price-change notices, drip-pricing compliance, and the French-language obligations. Apple's guidelines
say so directly: *"It is the developer's responsibility to understand and make sure their app
conforms with all local laws, not just the guidelines."*

## Canada / tax notes

- GST/HST registration is required once worldwide taxable supplies exceed **$30,000** (Ontario HST
  13%).
- **Registering hands us the Canadian Play remittance obligation:** Google's policy is explicit that
  *we* remit for Canadian sales once we give them a GST/HST ID; without one, Google remits.
- Selling direct via Stripe **removes the marketplace-facilitator shield** for US state sales tax and
  puts economic-nexus analysis across ~45 states on us. Stripe Tax Basic only calculates; filing is
  Tax Complete at ~C$120/month, which erases much of any link-out saving at our scale.
- Ontario's Consumer Protection Act 2023 is **not yet in force** (as of Jul 2026); BC and Quebec have
  live auto-renewal rules. Monthly terms (<60 days) avoid the heaviest advance-notice machinery, and
  store-billed subscriptions inherit Apple/Google's cancellation UI — a genuine compliance asset.

---

## Sequencing

| # | Work | Notes |
|---|---|---|
| 0 | **Decide prices** | PM call. Highest leverage, zero code risk |
| 1 | App Store Connect + Play Console: subscription groups / base plans; enable Apple **billing grace period**; leave **Family Sharing off** | ~1 day, account work |
| 2 | RevenueCat: products, entitlements, `purchases_flutter`, paywall | ~3 days |
| 3 | Backend: `subscriptions` + `processed_store_events`; one webhook → derive `users.tier`; reject sandbox writes | ~3 days |
| 4 | Trials, annual plans, cancellation link, auto-renewal disclosure copy | Covers BC/Quebec direction |
| 5 | GST/HST registration at $30k | Accounting, not code |
| 6 | *Later:* Stripe on the web app; US-gated iOS link-out **only** with annual pricing | Optional |

**None of this is blocked by E0.** Ads are gated behind Google OAuth verification + CASA (the long
pole); IAP has no such dependency. Given the marginal-cost problem, monetising first and letting ads
follow is the better order.

**Flutter floor:** Play Billing Library 8 is required for new apps/updates from Aug 2026 and needs
Flutter 3.44 / Dart 3.12. We are on **3.44.3** — clear, no upgrade needed.
