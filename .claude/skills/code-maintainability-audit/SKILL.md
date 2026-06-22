---
name: code-maintainability-audit
description: Use when reviewing or auditing Mamaflow backend code for maintainability and security — async correctness, Pydantic v2, UUID/UTC, defensive parsing, soft-delete, secrets, and dependency hygiene.
---

# Code & maintainability audit (Mamaflow backend)

The Mamaflow-specific checklist that `/code-review` and `/security-review` lean on. Stack: FastAPI +
SQLAlchemy 2.0 (async) + Pydantic v2 + Alembic. Firewall/PII data-flow is a separate concern — use
`firewall-privacy-audit` for that.

## Checklist

- **Async correctness:** no blocking/sync I/O on the event loop. Known offender:
  `gmail_reader.fetch_recent_emails` is synchronous (Google client) — wrap in `run_in_executor` or
  make the path async. DB access uses the async session, awaited.
- **Pydantic v2:** schemas at every API boundary (no raw dicts crossing layers); `model_validate` /
  `model_dump`; `Literal`/typed fields; validators where input is untrusted.
- **IDs & time:** UUID primary keys (no integer IDs); `TIMESTAMPTZ` stored in UTC; no naive/local
  datetimes.
- **Soft delete:** filter `deleted_at IS NULL` on reads; never hard-`DELETE` user data.
- **Defensive parsing:** external/LLM output parsed with fallbacks (extractor returns empty on bad
  JSON); handle empty inbox, missing subject/headers, malformed MIME.
- **Secrets:** config via `settings` from env; no secrets/tokens in code, logs, or the DB; `.env`
  gitignored; `.env.example` kept current with any new var.
- **Dependencies:** pinned/ranged in `backend/requirements.txt`; flag known-vulnerable versions; no
  unused heavy deps.
- **Errors:** correct HTTP status codes; no stack traces or PII leaked to responses/logs.
- **Clarity:** comment the *why*; small focused functions; no scaffolding outside the current task.

## How to use

Run as the lens for a review pass, then hand concrete findings to `/code-review` (correctness) and
`/security-review` (vulnerabilities). Report as must-fix / should-fix / nit with file:line.
