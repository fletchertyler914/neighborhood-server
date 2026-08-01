#!/usr/bin/env bash
# Print an online validation player on the running mc-lan container.
# Prefers AGENT_LIVE_PLAYER (default: firecrab93). Never picks a random friend.
# Output: bare player name (e.g. "firecrab93"); empty if preferred player is offline.
set -euo pipefail

container="${MC_CONTAINER:-mc-lan}"
preferred="${AGENT_LIVE_PLAYER:-firecrab93}"

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

# Normalize comma-separated names and look for the preferred validator only.
IFS=',' read -r -a names <<< "$list"
for name in "${names[@]}"; do
  trimmed="$(echo "$name" | tr -d '[:space:]')"
  [[ -z "$trimmed" ]] && continue
  if [[ "$(printf '%s' "$trimmed" | tr '[:upper:]' '[:lower:]')" == "$(printf '%s' "$preferred" | tr '[:upper:]' '[:lower:]')" ]]; then
    echo "$trimmed"
    exit 0
  fi
done

# Preferred player not online — do not fall back to friends.
exit 0
