#!/usr/bin/env bash
# firewall-guard.sh — deterministic guardrail for Mamaflow.
# Tripwire for the OBVIOUS firewall/privacy violations. NOT a proof — subtle
# leaks still need the security-auditor agent and human review. Kept intentionally
# tight (low false-positive) so a hard block always means a real problem.
#
# Usage:
#   scripts/firewall-guard.sh [file ...]   # scan given files
#   scripts/firewall-guard.sh              # scan all git-tracked files
# Exit codes: 0 = ok (warnings allowed), 2 = hard violation (blocks commit/edit).

set -u
RED=$'\033[31m'; YEL=$'\033[33m'; NC=$'\033[0m'
violations=0
warnings=0

# Resolve target files
if [ "$#" -gt 0 ]; then
  files="$*"
else
  files=$(git ls-files 2>/dev/null || find . -type f)
fi

for f in $files; do
  [ -f "$f" ] || continue
  case "$f" in *.md|*.lock|*.png|*.jpg|*.svg) continue;; esac
  # Skip the guardrail tooling itself — it legitimately contains the forbidden
  # pattern strings inside its own checks, and would otherwise flag itself.
  case "$f" in */firewall-guard.sh|firewall-guard.sh|*/firewall-hook.sh|firewall-hook.sh|*/pre-commit|*/setup-dev.sh) continue;; esac

  # --- HARD BLOCKS ---

  # 1. Killed ad-profile modules must never be referenced.
  if grep -nE 'ad_profile_builder|deals_matcher|deals_builder' "$f" >/dev/null 2>&1; then
    echo "${RED}BLOCK${NC} $f references a killed ad-profile module (ad_profile_builder/deals_matcher)."
    grep -nE 'ad_profile_builder|deals_matcher|deals_builder' "$f" | sed 's/^/      /'
    violations=$((violations+1))
  fi

  # 2. Hardcoded OAuth tokens.
  if grep -nE '(access_token|refresh_token)\s*=\s*["'"'"'](ya29\.|1//)' "$f" >/dev/null 2>&1; then
    echo "${RED}BLOCK${NC} $f looks like it hardcodes an OAuth token. Tokens go in Secret Manager."
    violations=$((violations+1))
  fi

  # 3. Ad-layer files must not touch content/event/child data.
  #    Heuristic: file path is in an ad area AND references event/child_name/extraction identifiers.
  case "$f" in
    # Test/spec files legitimately name forbidden terms to assert isolation — they don't ship. Skip.
    *_test.dart|*_test.py|*.test.ts|*.test.tsx|*.spec.ts|*.spec.tsx|*/test/*|*/tests/*) : ;;
    *ad/*|*ads/*|*advert*|*Ad.tsx|*Ads.tsx|*ad_*.py|*_ads.py|*_ad.dart|*ad_*.dart|*Ad.dart|*_ads.dart)
      if grep -nEi '\b(event|child_name|childName|extraction|email_body|email_content|category)\b' "$f" >/dev/null 2>&1; then
        echo "${RED}BLOCK${NC} $f is in the ad layer but references content/event/child data. Firewall violation."
        grep -nEi '\b(event|child_name|childName|extraction|email_body|email_content|category)\b' "$f" | sed 's/^/      /'
        violations=$((violations+1))
      fi
      ;;
  esac

  # --- WARNINGS (non-blocking) ---

  # 4. format="full" should be metadata-first in the Gmail reader.
  if grep -nE 'format\s*=\s*["'"'"']full' "$f" >/dev/null 2>&1; then
    echo "${YEL}WARN ${NC} $f uses format=full. Confirm the sender already passed the blocklist (metadata-first)."
    warnings=$((warnings+1))
  fi

  # 5. Possible raw email body persistence.
  if grep -nEi '(raw_body|email_body|message_body).*(Column|=\s*db|\.add\(|INSERT)' "$f" >/dev/null 2>&1; then
    echo "${YEL}WARN ${NC} $f may persist a raw email body. Only structured extractions should be stored."
    warnings=$((warnings+1))
  fi
done

echo "----"
if [ "$violations" -gt 0 ]; then
  echo "${RED}firewall-guard: $violations hard violation(s). Fix before committing.${NC}"
  exit 2
fi
if [ "$warnings" -gt 0 ]; then
  echo "${YEL}firewall-guard: $warnings warning(s) — review, not blocked.${NC}"
fi
echo "firewall-guard: ok"
exit 0
