# Mamaflow — AI assistant setup (Claude Code + Antigravity)

Persistent scaffolding so Claude Code and Antigravity always follow Mamaflow's rules —
especially the content/ad firewall, which is enforced *deterministically*, not just by
asking the model nicely.

> Installed in this repo on 2026-06-22. Layout adapted to the `backend/` + `frontend/` monorepo
> (the backend package stays `api`). Canonical rules: `AGENTS.md`. Decision log: `DECISIONS.md`.

## The idea in one picture

```
                 AGENTS.md  ──────────────►  read by Claude Code, Antigravity, Cursor
                (canonical)                   (the single source of truth)
                    │
        ┌───────────┼───────────────┐
        │           │               │
   CLAUDE.md     GEMINI.md     .agents/rules/*.md   ← thin, tool-specific, defer to AGENTS.md
   (Claude)    (Antigravity)    (Antigravity "Always On")
        │
   .claude/  ── settings.json (hooks) · agents/ · skills/ · commands/

   scripts/firewall-guard.sh   ← the deterministic guardrail
        ├── wired as a Claude Code PostToolUse hook (.claude/settings.json)
        └── wired as a git pre-commit hook (.githooks/pre-commit)  ← universal backstop
```

## Two layers of enforcement (this is the whole point)

1. SOFT — the model reads it and follows: AGENTS.md, CLAUDE.md, GEMINI.md, .agents/rules,
   skills, subagents. Good for guidance, not a guarantee. A prompted rule can fail under
   pressure, in long sessions, or via a prompt injection in a file the agent reads.
2. HARD — a script mechanically blocks the violation: scripts/firewall-guard.sh, run on
   every edit (Claude hook) and every commit (git hook). The firewall lives here because
   breaking it fails Google verification — it can't be left to "the model will remember."

The git pre-commit hook is the real backstop: it runs no matter which tool (or human)
wrote the code, so the guarantee holds in Antigravity too, where there is no deterministic
hook system.

## Install

Copy these into the Mamaflow repo root (merge, don't overwrite, any existing files), then:

Everything lives at the **repo root**, alongside `backend/` and `frontend/` (monorepo).

```bash
# 1. One-time bootstrap (activates the firewall git hook + makes scripts executable).
#    core.hooksPath is a LOCAL git setting and is not committed, so every fresh
#    clone runs this once.
bash scripts/setup-dev.sh

# 2. Claude Code picks up CLAUDE.md, .claude/settings.json, agents, skills, commands
#    automatically. On first open it will ask you to approve the project hooks — approve once.

# 3. Antigravity reads AGENTS.md and .agents/rules automatically. If a rule doesn't
#    appear, check Agent Manager -> ... -> Customizations -> Rules, and confirm the
#    .agents/rules path matches your Antigravity version (some builds use .agent/rules).
```

Optional (once the frontend exists): hang the bootstrap off it so `npm install` activates hooks too —
add to `frontend/package.json`:

```json
{ "scripts": { "postinstall": "bash ../scripts/setup-dev.sh" } }
```

## Monorepo layout

```
mamaflow/
├── AGENTS.md  CLAUDE.md  GEMINI.md  DECISIONS.md  HANDOFF.md  AI-SETUP.md  .gitignore
├── .claude/  .agents/  scripts/  .githooks/
├── infra/         Terraform (GCP project, OAuth)
├── backend/       FastAPI (package `api`)
└── frontend/      client app — platform under review (see DECISIONS.md); not created yet
```

The guard scans staged files across both `backend/` and `frontend/` in one commit, so the
firewall is checked on the backend and frontend together — the main reason to keep
them in one repo.

## File-by-file

| File | Tool | Role |
|------|------|------|
| AGENTS.md | all | Canonical rules. Edit here. Everything else defers to it. |
| CLAUDE.md | Claude Code | Imports AGENTS.md; points to hooks/agents/skills/commands. |
| GEMINI.md | Antigravity | Antigravity-only notes; defers to AGENTS.md. |
| .agents/rules/firewall.md | Antigravity | The firewall, Always On. |
| .agents/rules/privacy-and-stack.md | Antigravity | Privacy/data/stack, Always On. |
| .agents/skills/email-extraction.md | Antigravity | Extraction skill (mirror). |
| .agents/workflows/firewall-check.md | Antigravity | /firewall-check workflow. |
| .claude/settings.json | Claude Code | Registers the firewall hook + safe permissions. |
| .claude/agents/security-auditor.md | Claude Code | Subagent: firewall/privacy review. |
| .claude/agents/code-reviewer.md | Claude Code | Subagent: general review. |
| .claude/skills/email-extraction/SKILL.md | Claude Code | Extraction skill. |
| .claude/skills/firewall-privacy-audit/SKILL.md | Claude Code | Skill: content→ad firewall + PII data-flow self-check. |
| .claude/skills/testing/SKILL.md | Claude Code | Skill: pytest conventions; mock Anthropic/Gmail. |
| .claude/skills/code-maintainability-audit/SKILL.md | Claude Code | Skill: async/Pydantic/UUID-UTC/secrets checklist. |
| .claude/skills/db-migrations/SKILL.md | Claude Code | Skill: Alembic + SQLAlchemy model conventions. |
| .claude/commands/firewall-check.md | Claude Code | /firewall-check command. |
| .claude/commands/phase-status.md | Claude Code | /phase-status command. |
| scripts/firewall-guard.sh | all | Deterministic check (tripwire). |
| scripts/firewall-hook.sh | Claude Code | Adapter feeding edited file to the guard. |
| .githooks/pre-commit | all (git) | Universal backstop. |

## Keeping it honest

- AGENTS.md is canonical. Don't let the tool-specific files drift from it; when a rule
  changes, change AGENTS.md and re-derive.
- The guard is a tripwire for obvious cases, not a proof. Subtle data-flow leaks still
  need @security-auditor and human review.
- Keep the setup small enough that you can explain why every file exists. If a piece isn't
  earning its place, delete it.

## Verify the moving parts against current docs

These products change. Before relying on exact schemas, confirm:
- Claude Code hooks/agents/skills format: https://code.claude.com/docs
- Antigravity rules location (.agents/rules vs .agent/rules) for your version: https://antigravity.google/docs
