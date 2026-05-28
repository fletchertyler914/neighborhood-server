#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export AGENT_LIVE_TOOL_TESTS=1
if [[ -z "${AGENT_LIVE_TOOL_PLAYER:-}" && -n "${1:-}" ]]; then
  AGENT_LIVE_TOOL_PLAYER="$1"
fi
if [[ -z "${AGENT_LIVE_TOOL_PLAYER:-}" ]]; then
  AGENT_LIVE_TOOL_PLAYER="$(./scripts/_detect_player.sh 2>/dev/null || true)"
fi
export AGENT_LIVE_TOOL_PLAYER="${AGENT_LIVE_TOOL_PLAYER:-}"

if [[ -z "${AGENT_LIVE_TOOL_PLAYER}" ]]; then
  echo "AGENT_LIVE_TOOL_PLAYER is not set and no online player detected;" >&2
  echo "player-relative tests will be skipped." >&2
  echo "Usage: AGENT_LIVE_TOOL_PLAYER=<name> $0" >&2
fi

cd "$REPO_ROOT"
PYTHONPATH="$REPO_ROOT" python3 -m pytest tests/integration/test_live_tools.py -q
