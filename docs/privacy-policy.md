> Canonical public copy: `website/privacy.html` (served at /privacy on the production domain).
> Keep both in sync — edit here first, then re-transcribe.

# Mamaflow Privacy Policy (DRAFT — PM review required before publishing)

_Last updated: 2026-07-10. Status: DRAFT for Google OAuth verification (E0). Replace
bracketed placeholders and host at a public URL (e.g. https://mamaflow.app/privacy or the
Railway domain) before submitting for verification._

Mamaflow ("we", "our") helps parents turn family-related emails into a calendar and to-do
list. This policy explains what data we access, what we do with it, and — just as
importantly — what we never do with it.

## The short version

- We read your Gmail **only** to find family events and tasks (school, medical, activities).
- We **never store your emails**. Only the structured event we extract (title, date, time,
  location, child's first name as written, event type) is saved.
- Your email content is **never used for advertising** — not directly, not summarized, not
  inferred. This is a structural guarantee, not a promise.
- You can disconnect Gmail and delete your data at any time.

## What we access

With your explicit consent, Mamaflow requests **read-only** access to your Gmail
(`gmail.readonly`). We also receive your email address and basic profile from Google
Sign-In to create your account.

## How the processing works

1. We first read only message **headers** (sender, subject, date). Senders on our
   financial/promotional blocklist are excluded **before their message content is ever
   fetched**.
2. For remaining messages, the content is processed **in memory** to remove sensitive
   numbers (credit cards, bank accounts, government IDs) before any further processing.
3. The redacted text is sent to Anthropic's Claude API solely to extract structured event
   data (Anthropic does not train on this data per their commercial API terms).
4. Only the structured result is stored: event title, date, time, location, child name as
   written, event category, sender address, and a link back to the email in your own Gmail.

## What we never do

- **Never store raw email bodies** — they are processed in memory and discarded.
- **Never use email content (or anything derived from it) for advertising or ad
  targeting.** If Mamaflow shows ads, they are non-personalized or targeted only on
  non-content signals (e.g. app screen, coarse location) — never on anything from your inbox.
- **Never sell your data** or share it with data brokers.
- **Never keep your Google tokens on your device or in our application database** — they are
  held server-side in a secrets vault.

## Limited Use disclosure (Google API Services)

Mamaflow's use and transfer of information received from Google APIs adheres to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the **Limited Use** requirements. Specifically: Gmail data is used only to
provide the user-facing calendar/to-do feature the user requested; it is not used for
advertising; it is not sold; humans do not read it except with your explicit consent, for
security purposes, or to comply with law; and transfers are limited to the processing
described above (Anthropic as a data processor for extraction).

## Data retention & deletion

- Extracted items are retained until you delete them or your account.
- Account deletion soft-deletes then purges your data within [30] days.
- Disconnecting Gmail (in Mamaflow or at https://myaccount.google.com/permissions)
  immediately stops all processing; you may separately request deletion of extracted items.

## Sub-processors

| Provider | Purpose |
|---|---|
| Google (Gmail API, Sign-In) | mailbox access you authorize; authentication |
| Anthropic (Claude API) | event extraction from redacted text (no training on data) |
| Railway (hosting) + PostgreSQL | application hosting and storage of structured items |
| Google Cloud Secret Manager | server-side storage of OAuth tokens |
| Google Firebase Cloud Messaging (FCM/APNs) | delivery of reminder notifications; notification text contains the titles/times of your extracted items (e.g. an event name), transmitted only to your registered devices — never used for advertising |

## Contact

[Contact email — e.g. privacy@optimacore.io]

## Changes

We will post any changes here and update the date above. Material changes will be
announced in the app.
