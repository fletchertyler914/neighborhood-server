#!/usr/bin/env bash
# Build NeighborhoodAgent Paper plugin and install into data/plugins/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="$ROOT/plugins/neighborhood-agent"
OUT="$ROOT/data/plugins"

cd "$PLUGIN_DIR"

if [[ -x ./gradlew ]]; then
  ./gradlew jar --no-daemon
else
  if ! command -v gradle >/dev/null 2>&1; then
    echo "gradle not found. Install Gradle or add gradlew to $PLUGIN_DIR" >&2
    exit 1
  fi
  gradle jar --no-daemon
fi

JAR="$(find build/libs -name 'NeighborhoodAgent.jar' -print -quit)"
[[ -n "$JAR" ]] || { echo "JAR not found under build/libs" >&2; exit 1; }

mkdir -p "$OUT"
cp -f "$JAR" "$OUT/NeighborhoodAgent.jar"
echo "Installed $OUT/NeighborhoodAgent.jar"
echo "Restart mc-lan or run: docker compose restart mc"
