# Mamaflow — Claude Code Instructions
**BetterSaas Venture | Phase 0**

---

## What This Project Is

Mamaflow is a family operations assistant PWA for busy moms. It connects to Gmail, reads family-related emails (school, doctors, activities, playdates, summer planning), and surfaces structured, actionable events in a clean interface.

This is a real product. Build it like one.

---

## Who Is Building This

Akhil is a technical PM — he directs builds, reviews output, and makes architecture decisions. He does not write code from scratch. Your job is to build correctly, explain trade-offs clearly, and move one step at a time. Never pre-empt the next step. Build what is asked, stop, wait for confirmation.

---

## Core Architecture (read before touching anything)

```
Gmail OAuth → Email ingestion → Sender blocklist (Layer 1) →
Presidio PII redaction (Layer 2) → Category allowlist (Layer 3) →
Prompt injection wrap → Claude API extraction →
Structured events → PostgreSQL → React PWA
```

**DataBridge pattern:**
- Email Shim: public-facing, no credentials, wraps content, forwards to broker
- Email Broker: private, holds OAuth tokens, calls Gmail API, runs privacy pipeline, calls Claude
- These two are separate services. The shim never holds a token. Ever.

**PII rules (non-negotiable):**
- Raw email body is NEVER stored in the database
- OAuth tokens are NEVER stored in the database — Secret Manager reference only
- Financial emails are blocked at Layer 1 before the body is ever fetched
- Presidio redacts account numbers, card numbers, government IDs before Claude sees anything

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+ / FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.0 + Alembic migrations |
| Auth | Google OAuth 2.0 + PyJWT |
| AI | Claude API (claude-sonnet-4-20250514) |
| PII redaction | Microsoft Presidio |
| Email | Gmail API (google-auth, google-api-python-client) |
| Frontend | React + Vite PWA + Tailwind CSS |
| Payments | Stripe |
| Hosting | Railway (API) + Vercel (PWA) |

---

## Project Structure

```
mamaflow/
├── api/
│   ├── auth/
│   ├── routers/
│   ├── services/
│   │   ├── email_shim.py
│   │   ├── email_broker.py
│   │   ├── ai_extractor.py
│   │   ├── content_safety.py
│   │   ├── sender_blocklist.py
│   │   ├── privacy_pipeline.py
│   │   ├── ad_profile_builder.py
│   │   ├── deals_matcher.py
│   │   └── stripe_service.py
│   ├── models/
│   ├── schemas/
│   ├── db/
│   ├── config/
│   │   └── blocked_domains.json
│   └── main.py
├── pwa/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   └── config/
│   │       └── copy.ts
│   └── public/
│       └── manifest.json
├── DECISIONS.md
├── CLAUDE.md         ← this file
├── .env.example
├── .gitignore
└── README.md
```

---

## Development Rules

1. **One step at a time.** Build what is asked. Stop. Wait for confirmation before the next step.
2. **Never store secrets in code.** All credentials go in `.env` (gitignored). Provide `.env.example` with placeholder values.
3. **Always write `.env.example`** alongside any new environment variable.
4. **Migrations over raw SQL.** All schema changes go through Alembic.
5. **Pydantic schemas for all API boundaries.** No raw dicts passed between layers.
6. **Soft deletes everywhere.** Never `DELETE` a row that has user data. Use `deleted_at` timestamp.
7. **UUIDs as primary keys.** No integer IDs.
8. **UTC timestamps everywhere.** No local time in the database.
9. **Test the happy path first.** Get it working end-to-end, then add error handling.
10. **Comment the why, not the what.** Code should explain decisions, not re-state what the code does.

---

## Git Conventions (Conventional Commits)

```
feat: add Gmail OAuth flow
fix: handle missing email subject in extractor
chore: add Alembic migration for events table
docs: update CLAUDE.md with Phase 1 instructions
refactor: extract sender blocklist into separate service
```

Commit after each working step. Small commits, clear messages.

---

## Environment Variables

```bash
# API
DATABASE_URL=postgresql://user:password@localhost:5432/mamaflow
SECRET_KEY=your-jwt-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15

# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback

# Claude API
ANTHROPIC_API_KEY=your-anthropic-api-key

# Stripe (Phase 2)
STRIPE_SECRET_KEY=your-stripe-secret-key
STRIPE_WEBHOOK_SECRET=your-stripe-webhook-secret

# Environment
ENVIRONMENT=development
```

---

## Phase 0 — What We Are Building Right Now

**Goal:** Prove that Gmail OAuth + Claude extraction works end-to-end on real emails.

**Done when:** A real Gmail inbox is read, 10+ emails are processed through the privacy pipeline, and Claude returns structured JSON events that look correct.

**Phase 0 steps in order:**

1. Project scaffolding — folder structure, `requirements.txt`, `.env.example`, `.gitignore`
2. FastAPI app skeleton — `main.py` boots, `/health` endpoint returns 200
3. Gmail OAuth flow — user hits `/auth/google`, authenticates, token stored (in memory for Phase 0, Secret Manager in prod)
4. Gmail reader — fetch last 30 days of inbox, return raw email list
5. Sender blocklist — filter out blocked domains before fetching body
6. Presidio redaction — run email body through PII redaction before anything else sees it
7. Prompt injection wrapper — wrap sanitized content in structured prompt
8. Claude extraction — call Claude API, parse JSON response
9. Terminal output — print extracted events to terminal as formatted JSON
10. End-to-end test — run against 10 real emails, review output quality

**Phase 0 does NOT include:**
- Database (PostgreSQL comes in Phase 1)
- Frontend (PWA comes in Phase 2)
- Stripe or ads (Phase 2+)
- Deployment (local only for Phase 0)

---

## Key Decisions Already Made (do not re-litigate)

| # | Decision |
|---|---|
| D1 | Gmail OAuth first, Yahoo second |
| D2 | Shim/broker split — shim never holds credentials |
| D3 | Wrap-by-default prompt injection defense |
| D4 | OAuth tokens never in database |
| D5 | Raw email body never stored |
| D9 | PWA only — no App Store native wrapper |
| D13 | Sender blocklist is structural, not a user setting |
| D14 | Microsoft Presidio for PII redaction |
| D19 | Ad targeting from ad_profiles only, never email content |
| D20 | PWA only — no App Store |

---

## When You Are Unsure

- Check DECISIONS.md before proposing a new architectural direction
- Flag trade-offs explicitly — don't silently pick one
- If a decision affects security or PII handling, stop and ask before proceeding
- Prefer reversible decisions over irreversible ones

---

*Mamaflow CLAUDE.md — updated for Phase 0*
