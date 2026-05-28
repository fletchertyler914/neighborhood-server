#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export AGENT_LIVE_TOOL_TESTS=1
export AGENT_LIVE_TOOL_PLAYER="${AGENT_LIVE_TOOL_PLAYER:-${1:-}}"

if [[ -z "${AGENT_LIVE_TOOL_PLAYER}" ]]; then
  echo "AGENT_LIVE_TOOL_PLAYER is not set; player-relative tests will be skipped." >&2
  echo "Usage: AGENT_LIVE_TOOL_PLAYER=firecrab93 $0" >&2
fi

cd "$REPO_ROOT"
PYTHONPATH="$REPO_ROOT" python3 -m pytest tests/integration/test_live_tools.py -q
