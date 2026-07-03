---
activation: Always On
description: Mamaflow content/ad firewall — the rule that must never break.
---

# Firewall (Always On)

No user content of any kind — email, school data, health docs, photos, or any summary,
keyword, or inferred interest derived from them — may EVER reach the ad system.

- Ads target only non-content signals: coarse geo, app screen/context, user-typed profile
  fields not derived from content, and Google's own ad-profile data.
- Ad SDK is frontend-only and structurally isolated from event/child components.
- No server-side ad-targeting parameter is built from content.
- ad_profile_builder / deals_matcher are killed — never reference them.

This is enforced deterministically by the git pre-commit hook (scripts/firewall-guard.sh),
which runs no matter which tool wrote the code. Do not work around it. Full context: @/AGENTS.md
