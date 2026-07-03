---
description: Run the deterministic firewall guard across the repo and summarize findings.
allowed-tools: Bash(bash scripts/firewall-guard.sh:*)
---

Run `bash scripts/firewall-guard.sh` over all tracked files. Summarize any BLOCK and WARN
lines, grouped by file, and for each BLOCK propose the minimal fix. Then note that the
script is a tripwire only and recommend invoking @security-auditor for data-flow review
if the change touched the ad layer, Gmail reader, extractor, or persistence.
