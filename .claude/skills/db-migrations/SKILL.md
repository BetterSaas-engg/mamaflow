---
name: db-migrations
description: Use when creating or editing Alembic migrations or SQLAlchemy models in Mamaflow — UUID PK, TIMESTAMPTZ/UTC, soft-delete, async env conventions, and the autogenerate→review→upgrade flow.
---

# Database migrations (Mamaflow)

All schema changes go through Alembic — never raw SQL against the DB. Run from `backend/` (so the
`api` package and `alembic.ini` resolve). Async migration runner lives in `backend/alembic/env.py`.

## Model conventions

New models inherit the shared base in `backend/api/models/base.py` (`Base` + `TimestampMixin`), which
provides:
- **UUID primary key** (no integer IDs).
- **`created_at` / `updated_at`** as `TIMESTAMPTZ`, UTC.
- **`deleted_at`** for soft delete — filter `deleted_at IS NULL` on reads; never hard-`DELETE`.

Add the column types you need with explicit `nullable`, server defaults where sensible, and
`CHECK`/unique constraints in the model so autogenerate emits them.

## Workflow

```bash
cd backend
python -m alembic revision --autogenerate -m "create <table>"   # generate
# REVIEW the generated file in alembic/versions/ before applying:
#  - both upgrade() AND downgrade() are correct and reversible
#  - UUID PK + TIMESTAMPTZ + deleted_at present
#  - no accidental drops; constraints/indexes named
python -m alembic upgrade head      # apply
python -m alembic downgrade -1      # verify it reverses cleanly, then re-upgrade
```

Seed data is separate from schema: `python -m api.db.seed` (idempotent), not a migration.

## Common mistakes

- Editing tables by hand instead of a migration.
- Trusting autogenerate blindly — it misses some constraint/type changes and writes weak
  `downgrade()`s. Always read and fix the generated file.
- Naive `DateTime` instead of `TIMESTAMPTZ`/UTC; integer IDs instead of UUID.
- A migration that can't downgrade. If it truly can't, say so explicitly in the file.
