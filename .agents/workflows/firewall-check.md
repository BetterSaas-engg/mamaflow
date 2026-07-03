---
description: Run the firewall guard and summarize findings (/firewall-check).
---

1. Run `bash scripts/firewall-guard.sh` in the terminal.
2. Summarize BLOCK/WARN lines by file; for each BLOCK propose the minimal fix.
3. The script is a tripwire only — for ad-layer / Gmail / extractor / persistence changes,
   do a manual data-flow review against the firewall rule in @/AGENTS.md before finishing.
