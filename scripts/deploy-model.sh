#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-neighborhood-qwen2.5-7b:v1}"
ENV_FILE="${ENV_FILE:-.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  touch "$ENV_FILE"
fi

python3 - "$ENV_FILE" "$MODEL" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
model = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
out = []
seen = False
for line in lines:
    if line.startswith("OLLAMA_MODEL="):
        out.append(f"OLLAMA_MODEL={model}")
        seen = True
    else:
        out.append(line)
if not seen:
    out.append(f"OLLAMA_MODEL={model}")
path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY

docker compose up -d --build mc-agent
echo "deployed OLLAMA_MODEL=$MODEL"
