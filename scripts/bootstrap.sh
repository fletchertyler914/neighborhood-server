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

set_env_value() {
  local key="$1" value="$2"
  python3 - <<PY
import pathlib
import re
p = pathlib.Path(".env")
text = p.read_text()
key = "${key}"
value = "${value}"
if re.search(rf"^{re.escape(key)}=", text, re.M):
    text = re.sub(rf"^{re.escape(key)}=.*$", f"{key}={value}", text, flags=re.M)
else:
    text = text.rstrip() + f"\n{key}={value}\n"
p.write_text(text)
PY
}

remove_env_key() {
  local key="$1"
  python3 - <<PY
import pathlib
import re
p = pathlib.Path(".env")
text = p.read_text()
text = re.sub(r"^${key}=.*\n?", "", text, flags=re.M)
p.write_text(text)
PY
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
  warn "ollama not found on the host"
  HAS_OLLAMA=0
fi

OLLAMA_MODE="${BOOTSTRAP_OLLAMA:-}"
if [[ -z "$OLLAMA_MODE" ]]; then
  if (( HAS_OLLAMA == 1 )); then
    OLLAMA_MODE=host
  elif [[ -t 0 ]]; then
    echo
    echo "How should /agent reach the LLM?"
    echo "  1) Host Ollama (install from https://ollama.com — best on Mac for GPU)"
    echo "  2) Docker Compose ollama profile (bundled; no host install)"
    read -r -p "Choice [1/2] (default 2): " choice
    case "${choice:-2}" in
      1|host) OLLAMA_MODE=host ;;
      *) OLLAMA_MODE=profile ;;
    esac
  else
    OLLAMA_MODE=profile
  fi
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
OLLAMA_BASE_URL=http://host.docker.internal:11434
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

case "$OLLAMA_MODE" in
  host)
    set_env_value "OLLAMA_BASE_URL" "http://host.docker.internal:11434"
    remove_env_key "COMPOSE_PROFILES"
    ok "OLLAMA_BASE_URL → host Ollama (http://host.docker.internal:11434)"
    USE_OLLAMA_PROFILE=0
    ;;
  profile|compose|docker)
    set_env_value "OLLAMA_BASE_URL" "http://ollama:11434"
    set_env_value "COMPOSE_PROFILES" "ollama"
    ok "OLLAMA_BASE_URL → Compose ollama service (http://ollama:11434)"
    ok "COMPOSE_PROFILES → ollama (plain make up will include bundled Ollama)"
    USE_OLLAMA_PROFILE=1
    ;;
  *)
    err "Unknown BOOTSTRAP_OLLAMA=$OLLAMA_MODE (use host or profile)"
    exit 1
    ;;
esac

if (( HAS_OLLAMA == 1 )) && [[ "$OLLAMA_MODE" == host ]]; then
  if ! ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -q "^qwen2.5:7b-instruct$"; then
    warn "qwen2.5:7b-instruct not pulled. Run: ollama pull qwen2.5:7b-instruct"
  else
    ok "qwen2.5:7b-instruct already pulled"
  fi
fi

if (( USE_OLLAMA_PROFILE == 1 )); then
  warn "First boot with bundled Ollama pulls ~5GB; COMPOSE_PROFILES=ollama is set in .env"
fi

echo
echo "Next steps:"
printf "${DIM}"
if (( USE_OLLAMA_PROFILE == 1 )); then
  echo "  1. make up                                 # Paper + agent + bundled Ollama"
else
  echo "  1. make up                                 # Paper + agent (host Ollama must be running)"
fi
echo "  2. make plugin && make seed                # in-game plugin + schematic corpus"
echo "  3. ./mc.sh op <yourname>                   # op yourself (whitelist is on by default)"
echo "  4. /agent build me a small cabin           # in-game!"
printf "${RESET}"
