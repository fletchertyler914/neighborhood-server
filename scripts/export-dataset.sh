#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$REPO_ROOT/datasets/reviews/raw/export.jsonl}"

PYTHONPATH="$REPO_ROOT" python3 -m agent.eval.cli export \
  --repo-root "$REPO_ROOT" \
  --out "$OUT" \
  --report "$REPO_ROOT/data/eval-runs/latest/report.json" \
  --audit "$REPO_ROOT/data/agent-audit.log"

echo "wrote $OUT"
