#!/usr/bin/env bash
# Start/stop the Neighborhood Minecraft agent orchestrator on the host.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

UV="${UV:-$HOME/.local/bin/uv}"
if [[ ! -x "$UV" ]]; then
  UV="$(command -v uv || true)"
fi
[[ -x "$UV" ]] || { echo "uv not found. Install: https://docs.astral.sh/uv/" >&2; exit 1; }

# Load .env if present
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export NEIGHBORHOOD_REPO="$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

cmd="${1:-start}"
case "$cmd" in
  start)
    exec "$UV" run --script "$ROOT/agent/orchestrator.py"
    ;;
  health)
    curl -fsS "http://${AGENT_BIND_HOST:-127.0.0.1}:${AGENT_BIND_PORT:-8787}/health" && echo
    ;;
  *)
    echo "Usage: $0 {start|health}" >&2
    exit 1
    ;;
esac
