# Mamaflow — Developer Handoff (Phase 0 Complete)

**Date:** 2026-06-13
**Status:** Phase 0 complete. End-to-end pipeline verified against a live Gmail inbox.

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
| GET | `/api/v1/auth/google` | Start Gmail OAuth flow |
| GET | `/api/v1/auth/google/callback` | OAuth callback |
| GET | `/api/v1/sync/preview?email=` | Raw email list (no filtering) |
| GET | `/api/v1/sync/preview-filtered?email=` | Emails sorted into allowed/blocked/unknown with PII redaction |
| GET | `/api/v1/sync/extract?email=` | Full pipeline — returns structured events + actions per email |

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

```
api/
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

alembic/
├── env.py                          # Async migration runner
└── versions/
    └── f11c1892443a_create_sender_allowlist_and_sender_.py

tests/
└── test_content_wrapper.py         # 7 security tests for prompt injection defense
```

---

## Environment Setup

1. Copy `.env.example` to `.env` and fill in real values:
   - `DATABASE_URL` — Railway PostgreSQL connection string (standard `postgresql://` prefix; the app converts to `postgresql+asyncpg://` at runtime)
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — GCP OAuth 2.0 credentials with Gmail readonly scope
   - `ANTHROPIC_API_KEY` — Anthropic API key for Claude Sonnet 4.6
2. `pip install -r requirements.txt`
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
