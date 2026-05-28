#!/usr/bin/env bash
# Seed missing template schematics via fallback builds (requires live server + seed player).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export NEIGHBORHOOD_REPO="$ROOT"
python3 -m agent.templates.seed "$@"
