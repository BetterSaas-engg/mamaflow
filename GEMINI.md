# GEMINI.md — Mamaflow (Antigravity-only overrides)

The canonical rules are in @/AGENTS.md and .agents/rules/ — both are always on.
This file is only for Antigravity-specific behavior; it adds nothing that conflicts
with AGENTS.md. The firewall and privacy rules in AGENTS.md apply unchanged.

Antigravity note: Antigravity rules are advisory (model-following), not deterministic.
The deterministic firewall guarantee comes from the git pre-commit hook
(scripts/firewall-guard.sh), which runs regardless of which tool wrote the code.
Make sure git hooks are installed (see README.md) so the guarantee holds in Antigravity too.
