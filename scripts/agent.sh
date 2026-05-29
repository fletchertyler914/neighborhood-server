#!/usr/bin/env bash
# Start/stop/inspect the Neighborhood Minecraft agent orchestrator.
#
# The canonical deployment runs the orchestrator as the `mc-agent` Compose
# service (`make up` / `docker compose up -d mc-agent`). This wrapper is
# kept for occasional host-side runs (debugging the FastAPI app outside
# Compose) and as a convenient health-check shortcut.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export NEIGHBORHOOD_REPO="$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

cmd="${1:-help}"
case "$cmd" in
  start)
    # Run the orchestrator on the host (not the usual path — prefer mc-agent).
    PY="${PYTHON:-python3}"
    exec "$PY" -m agent.orchestrator
    ;;
  compose-up)
    exec docker compose up -d --build mc-agent
    ;;
  restart)
    exec docker compose restart mc-agent
    ;;
  logs)
    exec docker compose logs -f mc-agent
    ;;
  health)
    HOST="${AGENT_BIND_HOST:-127.0.0.1}"
    PORT="${AGENT_BIND_PORT:-8787}"
    if [[ "$HOST" == "0.0.0.0" ]]; then
      HOST="127.0.0.1"
    fi
    curl -fsS "http://${HOST}:${PORT}/health" && echo
    ;;
  help|*)
    cat <<EOF
Usage: $0 {start|compose-up|restart|logs|health|help}

  start       Run python -m agent.orchestrator on the host (debug; not the
              normal path — production uses the mc-agent Compose service).
  compose-up  docker compose up -d --build mc-agent
  restart     docker compose restart mc-agent
  logs        docker compose logs -f mc-agent
  health      GET /health from the host-published orchestrator (defaults
              to 127.0.0.1:8787 when AGENT_BIND_HOST is unset / 0.0.0.0).
EOF
    [[ "$cmd" == help ]] && exit 0 || exit 1
    ;;
esac
