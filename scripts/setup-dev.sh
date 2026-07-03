#!/usr/bin/env bash
# One-time dev setup. Run after cloning: bash scripts/setup-dev.sh
# Activates the firewall git hook (core.hooksPath is local, never committed)
# and makes the scripts executable. Safe to run repeatedly.
set -e
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
chmod +x scripts/*.sh .githooks/* 2>/dev/null || true
echo "Mamaflow dev hooks active (core.hooksPath -> .githooks)."
echo "Running a firewall self-check..."
bash scripts/firewall-guard.sh || true
