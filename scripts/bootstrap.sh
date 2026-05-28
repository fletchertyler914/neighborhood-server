#!/usr/bin/env bash
# One-shot bootstrap for a fresh clone.
#
# Detects required tooling, generates secrets/.env if missing, optionally pulls
# a default Ollama model, and prints next steps.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

YELLOW='\033[33m'
GREEN='\033[32m'
RED='\033[31m'
DIM='\033[2m'
RESET='\033[0m'

ok()   { printf "  ${GREEN}✓${RESET} %s\n" "$*"; }
warn() { printf "  ${YELLOW}!${RESET} %s\n" "$*"; }
err()  { printf "  ${RED}✗${RESET} %s\n" "$*" >&2; }

require() {
  local name="$1" install_hint="$2"
  if command -v "$name" >/dev/null 2>&1; then
    ok "$name found"
    return 0
  fi
  err "$name is missing: $install_hint"
  return 1
}

echo "neighborhood-server bootstrap"
echo "============================="

missing=0
require docker         "https://docs.docker.com/get-docker/"            || missing=$((missing+1))
require docker-compose "(comes with Docker Desktop, or 'docker compose')" \
  || command -v "docker compose" >/dev/null 2>&1 \
  || warn "docker compose plugin not found; some scripts assume 'docker compose'"
require python3        "https://www.python.org/downloads/"              || missing=$((missing+1))
if (( missing > 0 )); then
  err "$missing required dependency(ies) missing — install them and re-run."
  exit 1
fi

if command -v ollama >/dev/null 2>&1; then
  ok "ollama found ($(ollama --version 2>/dev/null | head -1))"
  HAS_OLLAMA=1
else
  warn "ollama not found — the agent will fall back to OPENAI if you set OPENAI_API_KEY"
  warn "install from https://ollama.com to run a free, local model"
  HAS_OLLAMA=0
fi

if [[ ! -d "secrets" ]]; then
  mkdir -p secrets
fi
if [[ ! -f "secrets/rcon_password" ]]; then
  python3 -c "import secrets; print(secrets.token_urlsafe(24))" > secrets/rcon_password
  chmod 600 secrets/rcon_password
  ok "generated secrets/rcon_password"
else
  ok "secrets/rcon_password exists"
fi

if [[ ! -f ".env" ]]; then
  if [[ -f ".env.example" ]]; then
    cp .env.example .env
    if grep -q '^AGENT_API_TOKEN=' .env; then
      token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
      python3 - <<PY
import pathlib
p = pathlib.Path(".env")
text = p.read_text()
text = text.replace("change-me-to-a-long-random-string", "${token}")
p.write_text(text)
PY
    fi
    ok "created .env from .env.example with a fresh AGENT_API_TOKEN"
  else
    cat > .env <<EOF
AGENT_API_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
AGENT_BIND_HOST=0.0.0.0
AGENT_BIND_PORT=8787
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
OLLAMA_FALLBACK_MODEL=qwen3:8b
AGENT_LOCAL_MODEL_TIMEOUT_SEC=15
OLLAMA_NUM_CTX=4096
OLLAMA_NUM_PREDICT=512
EOF
    ok "wrote a minimal .env"
  fi
  warn "If you want playit.gg crossplay, add PLAYIT_SECRET_KEY=... to .env"
else
  ok ".env exists"
fi

if (( HAS_OLLAMA == 1 )); then
  if ! ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -q "^qwen2.5:7b-instruct$"; then
    warn "qwen2.5:7b-instruct not pulled. Run: ollama pull qwen2.5:7b-instruct"
  else
    ok "qwen2.5:7b-instruct already pulled"
  fi
fi

echo
echo "Next steps:"
printf "${DIM}"
echo "  1. ./mc.sh up                  # start the Paper server + agent"
echo "  2. ./scripts/seed-templates.sh # build all .schem files in-world"
echo "  3. ./mc.sh op <yourname>       # op yourself in-game"
echo "  4. /agent build me a small cabin   # in-game!"
printf "${RESET}"
