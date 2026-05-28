#!/usr/bin/env bash
# Minecraft server admin helper for the neighborhood-server Compose stack.
# Wraps `docker exec ... rcon-cli` and a few container operations.

set -euo pipefail

CONTAINER="${MC_CONTAINER:-mc-lan}"

usage() {
  cat <<'EOF'
Usage: ./mc.sh <command> [args...]

Player commands:
  op <name>           Make a player operator
  deop <name>         Remove operator status
  list                List currently connected players
  whitelist <name>    Add a player to the whitelist
  unwhitelist <name>  Remove a player from the whitelist
  kick <name> [msg]   Kick a player
  ban <name> [msg]    Ban a player
  pardon <name>       Unban a player

Server commands:
  say <message>       Broadcast a chat message
  gamemode <mode> [name]
                      Set gamemode (creative|survival|adventure|spectator)
  time <set|add> <value>
                      e.g. time set day, time add 1000
  weather <clear|rain|thunder> [duration]
  cmd <command...>    Run any raw RCON command
  console             Attach to the live interactive console
                      (detach with Ctrl-P then Ctrl-Q)
  logs                Tail the Minecraft server logs (Ctrl-C to stop)
  status              Show docker compose status for all services
  backup              Trigger an immediate world backup

Notes:
  - Bedrock players appear with a leading "." (Floodgate prefix), e.g. .LunarLicense582
  - Override container name with MC_CONTAINER=foo ./mc.sh ...

Examples:
  ./mc.sh op .LunarLicense582
  ./mc.sh op SomeJavaPlayer
  ./mc.sh say "Restarting in 5 minutes"
  ./mc.sh gamemode creative .LunarLicense582
  ./mc.sh cmd "time set day"
EOF
}

require_container() {
  if ! docker inspect -f '{{.State.Status}}' "$CONTAINER" >/dev/null 2>&1; then
    echo "Container '$CONTAINER' not found. Is it running? Try: docker compose up -d" >&2
    exit 1
  fi
}

rcon() {
  require_container
  docker exec -i "$CONTAINER" rcon-cli "$@"
}

cmd="${1:-}"
shift || true

case "$cmd" in
  op)          rcon op "$@" ;;
  deop)        rcon deop "$@" ;;
  list)        rcon list ;;
  whitelist)   rcon whitelist add "$@" ;;
  unwhitelist) rcon whitelist remove "$@" ;;
  kick)        rcon kick "$@" ;;
  ban)         rcon ban "$@" ;;
  pardon)      rcon pardon "$@" ;;
  say)         rcon say "$*" ;;
  gamemode)    rcon gamemode "$@" ;;
  time)        rcon time "$@" ;;
  weather)     rcon weather "$@" ;;
  cmd)         rcon "$*" ;;
  console)     require_container; exec docker attach --sig-proxy=false "$CONTAINER" ;;
  logs)        require_container; exec docker logs -f --tail 100 "$CONTAINER" ;;
  status)      docker compose ps ;;
  backup)
               require_container
               docker exec -i mc-backup backup now 2>/dev/null \
                 || docker exec -i mc-backup /opt/backup-loop.sh now \
                 || { echo "Could not trigger immediate backup; the next scheduled run will pick it up." >&2; exit 1; }
               ;;
  ""|help|-h|--help)
               usage ;;
  *)
               echo "Unknown command: $cmd" >&2
               echo
               usage
               exit 1
               ;;
esac
