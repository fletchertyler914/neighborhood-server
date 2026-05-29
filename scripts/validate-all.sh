#!/usr/bin/env bash
# One-command validation entrypoint for local development.
#
# Defaults to fast checks that do not mutate the world. Opt into live and full
# world validation with RUN_LIVE=1 / RUN_FULL_WORLD=1.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== unit / contract tests =="
PYTHONPATH="$ROOT" python3 -m pytest tests/ -q

echo
echo "== template ranking eval =="
PYTHONPATH="$ROOT" python3 -m agent.eval.template_ranking_eval

if [[ "${RUN_LIVE:-0}" == "1" ]]; then
  : "${AGENT_LIVE_TOOL_PLAYER:?set AGENT_LIVE_TOOL_PLAYER for live tool tests}"
  echo
  echo "== live tool integration =="
  AGENT_LIVE_TOOL_PLAYER="$AGENT_LIVE_TOOL_PLAYER" ./scripts/live-tool-tests.sh
fi

if [[ "${RUN_SPEC:-0}" == "1" ]]; then
  echo
  echo "== orchestrator spec eval =="
  ./scripts/eval.sh spec
fi

if [[ "${RUN_FULL_WORLD:-0}" == "1" ]]; then
  echo
  echo "== full world validation (catalog + mobs) =="
  PYTHONPATH="$ROOT" python3 scripts/full_validation.py
fi

echo
echo "validation complete"
