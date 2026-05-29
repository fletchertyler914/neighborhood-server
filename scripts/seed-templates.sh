#!/usr/bin/env bash
# Seed missing template schematics via fallback builds (requires live server + seed player).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export NEIGHBORHOOD_REPO="$ROOT"

has_player_arg=0
dry_run=0
for arg in "$@"; do
  case "$arg" in
    --player|--player=*)
      has_player_arg=1
      break
      ;;
    --dry-run)
      dry_run=1
      ;;
  esac
done

if [[ "$dry_run" == 0 && "$has_player_arg" == 0 && -z "${AGENT_SEED_PLAYER:-}" ]]; then
  detected="$("$ROOT/scripts/_detect_player.sh" 2>/dev/null || true)"
  if [[ -n "$detected" ]]; then
    export AGENT_SEED_PLAYER="$detected"
    echo "Using online player for template seeding: $AGENT_SEED_PLAYER"
  else
    echo "No online player detected for template seeding." >&2
    echo "Join the server as an OP, then run: make seed" >&2
    echo "Or pass one explicitly: AGENT_SEED_PLAYER=<name> make seed" >&2
    exit 1
  fi
fi

python3 -m agent.templates.seed "$@"
