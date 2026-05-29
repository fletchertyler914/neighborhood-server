#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS="${AGENT_COMPARE_MODELS:-qwen2.5:7b-instruct,qwen3:8b}"
ORCH_URL="${AGENT_ORCH_URL:-http://127.0.0.1:8787}"
TOKEN="${AGENT_API_TOKEN:-dev-change-me}"

PYTHONPATH="$REPO_ROOT" python3 -m agent.eval.cli compare \
  --repo-root "$REPO_ROOT" \
  --orchestrator-url "$ORCH_URL" \
  --api-token "$TOKEN" \
  --models "$MODELS" \
  --mode spec \
  --compare-baseline "$REPO_ROOT/agent/eval/baseline.strict.json"
