#!/usr/bin/env bash
# op.sh - grant operator status to one or more players over RCON.
#
# Usage:
#   ./op.sh <name> [name ...]
#
# Notes:
#   - Bedrock (Geyser/Floodgate) players need a leading "." prefix on their
#     gamertag, e.g. .LunarLicense582
#   - Override the container name with MC_CONTAINER=foo ./op.sh ...

set -euo pipefail

CONTAINER="${MC_CONTAINER:-mc-lan}"

if [ $# -eq 0 ]; then
  cat <<EOF
Usage: ./op.sh <name> [name ...]

Bedrock players need a leading "." (Floodgate prefix), e.g. .GamerTag123
EOF
  exit 1
fi

if ! docker inspect -f '{{.State.Status}}' "$CONTAINER" >/dev/null 2>&1; then
  echo "Container '$CONTAINER' is not running. Try: docker compose up -d" >&2
  exit 1
fi

for name in "$@"; do
  printf '%-32s ' "$name"
  docker exec -i "$CONTAINER" rcon-cli op "$name"
done
