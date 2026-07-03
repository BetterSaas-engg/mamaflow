---
description: Report what remains in the current build phase.
allowed-tools: Read, Grep, Glob
---

Read HANDOFF.md and DECISIONS.md. Report, concisely:
1. Current build state from HANDOFF.md — what's done, what's next, and any "Known issues" /
   deferred items.
2. Any code present that contradicts a locked decision in AGENTS.md/DECISIONS.md (and flag any
   decision currently marked "under review").
3. The single next task to do, with the files it touches.
Do not start work — just report.
