#!/usr/bin/env bash
# Print the first online player on the running mc-lan container.
# Output: bare player name (e.g. "Steve" or ".BedrockPlayer"); empty if none.
# Used by agent-smoke.sh / live-tool-tests.sh so the user never has to set
# AGENT_SMOKE_PLAYER manually for one-off runs.
set -euo pipefail

container="${MC_CONTAINER:-mc-lan}"

if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
  exit 0
fi

raw="$(docker exec -i "$container" rcon-cli list 2>/dev/null || true)"
if [[ -z "$raw" ]]; then
  exit 0
fi

# rcon-cli returns: "There are 1 of a max of 10 players online: name1, name2"
list="${raw#*online:}"
list="${list#*online :}"
if [[ "$list" == "$raw" ]]; then
  exit 0
fi

first="${list%%,*}"
first="${first// /}"
first="${first%[[:space:]]}"
echo "$first"
