#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-spec}"
shift || true

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT
export MODE

export AGENT_EVAL_MODE="${AGENT_EVAL_MODE:-1}"
export AGENT_EVAL_DISABLE_RETRIEVAL="${AGENT_EVAL_DISABLE_RETRIEVAL:-1}"
export AGENT_EVAL_DISABLE_DYNAMIC_CONTEXT="${AGENT_EVAL_DISABLE_DYNAMIC_CONTEXT:-1}"

ORCH_URL="${AGENT_ORCH_URL:-http://127.0.0.1:8787}"
TOKEN="${AGENT_API_TOKEN:-dev-change-me}"

ARGS=("$MODE" "--repo-root" "$REPO_ROOT" "--orchestrator-url" "$ORCH_URL" "--api-token" "$TOKEN")
if [[ -n "${EVAL_COMPARE_BASELINE:-}" ]]; then
  ARGS+=("--compare-baseline" "$EVAL_COMPARE_BASELINE")
fi
if [[ -n "${EVAL_SAVE_BASELINE:-}" ]]; then
  ARGS+=("--save-baseline" "$EVAL_SAVE_BASELINE")
fi

if python3 - <<PY >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("${ORCH_URL}/health", timeout=2).read()
PY
then
  PYTHONPATH="$REPO_ROOT" python3 -m agent.eval.cli run "${ARGS[@]}"
else
  for _ in {1..30}; do
    if docker exec mc-agent python - <<'PY' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8787/health", timeout=2).read()
PY
    then
      break
    fi
    sleep 1
  done
  EXTRA=()
  if [[ -n "${AGENT_EVAL_PLAYER:-}" ]]; then
    EXTRA+=("--player" "$AGENT_EVAL_PLAYER")
  fi
  if [[ -n "${AGENT_EVAL_UUID:-}" ]]; then
    EXTRA+=("--uuid" "$AGENT_EVAL_UUID")
  fi
  if [[ -n "${EVAL_CASE:-}" ]]; then
    EXTRA+=("--case" "$EVAL_CASE")
  fi
  docker exec \
    -e AGENT_EVAL_ALLOW_WORLD_MUTATION="${AGENT_EVAL_ALLOW_WORLD_MUTATION:-}" \
    -e AGENT_EVAL_DISABLE_RETRIEVAL="${AGENT_EVAL_DISABLE_RETRIEVAL:-1}" \
    -e AGENT_EVAL_DISABLE_DYNAMIC_CONTEXT="${AGENT_EVAL_DISABLE_DYNAMIC_CONTEXT:-1}" \
    mc-agent \
    python -m agent.eval.cli run "$MODE" \
      --repo-root /app \
      --orchestrator-url http://127.0.0.1:8787 \
      --json-out /app/data/eval-runs/latest \
      "${EXTRA[@]}"
fi

