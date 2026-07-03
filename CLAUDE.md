# CLAUDE.md — Mamaflow (Claude Code)

The canonical rules are in @AGENTS.md — read it first. It is always in effect. When a rule in
AGENTS.md and a request conflict, the rule wins. **The firewall is not negotiable.**

## Claude Code specifics

- **Deterministic guardrail:** `scripts/firewall-guard.sh` runs on every edit (PostToolUse hook in
  `.claude/settings.json`) and on every commit (git pre-commit hook). If it exits non-zero, fix the
  flagged code — do not disable the hook or edit settings to silence it.
- **Subagents:** `@security-auditor` before finishing any change that touches the ad layer, the
  Gmail reader, the Claude extractor, or data persistence. `@code-reviewer` for general review.
- **Skills** (auto-load by context, or invoke with `/name`):
  - `email-extraction` — how to write/modify the Claude extraction call.
  - `firewall-privacy-audit` — content→ad firewall + PII data-flow self-check.
  - `testing` — pytest conventions; mock the Anthropic/Gmail clients (never hit live APIs in tests).
  - `code-maintainability-audit` — async/Pydantic/UUID-UTC/secrets checklist.
  - `db-migrations` — Alembic + SQLAlchemy model conventions.
- **Commands:** `/firewall-check` runs the guard + summarizes; `/phase-status` reports remaining tasks.

## Project memory (file-based, durable — survives any context window)

These committed files ARE the project's long-term memory. Read them at the start of work; keep them
current:
- **@AGENTS.md** — rules/constraints (loaded every session).
- **DECISIONS.md** — the decision log / "why" (`D1…Dn`, append-only).
- **HANDOFF.md** — living build state: done / next / known issues.

After each working step, update `HANDOFF.md`. When you make a decision, append it to `DECISIONS.md`.

## Repo layout (monorepo)

```
mamaflow/
├── AGENTS.md  CLAUDE.md  GEMINI.md  DECISIONS.md  HANDOFF.md  AI-SETUP.md
├── .claude/  .agents/  scripts/  .githooks/   ← AI config + firewall guard (shared)
├── infra/                                      ← Terraform (GCP project, OAuth)
├── backend/                                    ← FastAPI; package is `api` (import path unchanged)
│   ├── api/  alembic/  alembic.ini  requirements.txt  tests/  .env.example
└── frontend/                                   ← future client (platform under review — see DECISIONS.md)
```

## Running the backend (from `backend/`)

```bash
cd backend
pip install -r requirements.txt
python -m alembic upgrade head     # create sender_allowlist / sender_blocklist tables
python -m api.db.seed              # seed default blocklist rows (idempotent)
uvicorn api.main:app --reload      # serve on :8000  → GET /health
python -m pytest                   # run the test suite
```

Environment variables: copy `backend/.env.example` → `backend/.env` and fill it in. `.env.example`
is the canonical list (DB URL, Google OAuth, Anthropic key, …). Never commit `.env`; never put
secrets or OAuth tokens in code or the DB.

## Conventions

- **Conventional Commits**, small and clear: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`.
  Commit after each working step.
- One step at a time — build what's asked, then stop. A technical PM directs the build and reviews
  output; explain trade-offs, don't silently pick one.
- Stack/style, PII rules, the firewall, and scope boundaries all live in @AGENTS.md.
