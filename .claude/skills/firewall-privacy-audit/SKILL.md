---
name: firewall-privacy-audit
description: Use when finishing a change that touches the ad layer, the Gmail reader, the Claude extractor, or anything that stores data — Mamaflow's content→ad firewall and PII/token data-flow self-check before commit.
---

# Firewall & privacy audit

The deterministic guard (`scripts/firewall-guard.sh`) is a tripwire for the obvious cases. This
skill is the **data-flow self-check** you run before finishing — tracing flows the regex can't see.
Canonical rules: @AGENTS.md (D19 firewall + privacy). Deep review: `@security-auditor`.

## When to use

- Editing anything under an ad path, the Gmail reader, `ai_extractor.py`/`content_wrapper.py`, or any
  DB write / persistence.
- Before `git commit` on those changes.

## Trace, don't pattern-match

1. **Content → ads?** Does any email text, extracted `FamilyItem`, child name, `event_type`, or any
   summary/inference derived from them flow toward the ad system — server OR client? It must not. Ad
   targeting uses ONLY non-content signals (coarse geo, app screen, user-typed profile, Google's
   ad-profile data). The ad SDK is frontend-only, isolated from event/child components.
2. **Raw body stored?** Only structured extractions persist. No raw/full email body in any DB write,
   log, or cache.
3. **Tokens?** No OAuth token in the DB, env files, or source (in-memory only for Phase 0).
4. **Fetch ordering?** Gmail is `format="metadata"` → blocklist check → `format="full"` only for
   senders that pass. A blocked sender's body is never fetched.
5. **Injection?** Email body is wrapped as untrusted data, never treated as instructions.

## Finish

- Run `bash scripts/firewall-guard.sh` (or `/firewall-check`); resolve every BLOCK, review WARNs.
- For ad-layer / Gmail / extractor / persistence changes, invoke `@security-auditor` for the deep
  data-flow review — the script alone is not sufficient.

## Red flags — stop

- "It's just metadata / a category / an aggregate, not content." (Derivations count. It's content.)
- "The ad call is on the client, so it's fine." (Trace what data reached the client.)
- Referencing `ad_profile_builder` / `deals_matcher` / `deals_builder` (killed — never reference).
- Persisting an email body "temporarily." Logging redacted PII values.
