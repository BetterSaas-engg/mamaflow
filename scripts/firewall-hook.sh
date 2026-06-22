#!/usr/bin/env bash
# Adapter so Claude Code's PostToolUse hook can run firewall-guard on the file
# that was just edited. Reads the hook JSON from stdin, extracts the file path,
# and runs the guard. Exit 2 is fed back to Claude to fix the change.
set -u
root="${CLAUDE_PROJECT_DIR:-.}"
path=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path","") or "")' 2>/dev/null)
[ -z "$path" ] && exit 0
exec bash "$root/scripts/firewall-guard.sh" "$path"
