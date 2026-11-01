# Public quickstart

Fresh clone → playing with the local `/agent` sidekick. For party ops
(whitelist, GriefPrevention, backups), see [HOSTING.md](HOSTING.md). Full
setup story: [README](../README.md).

## Prerequisites

- Docker Desktop (macOS / Windows) or Docker Engine + Compose v2 (Linux)
- Python 3.11+ (for `make bootstrap`)
- ~6 GB free RAM, ~5 GB free disk
- A local LLM via [Ollama](https://ollama.com):
  - **Mac Apple Silicon (recommended):** `gemma4:12b-mlx`
  - **Non-Mac / no MLX:** e.g. `qwen2.5:7b-instruct` (slower model path)
  - **Or** the bundled Compose `ollama` profile (no host install)

There is **no cloud LLM fallback** for the sidekick.

## 1. Bootstrap

```bash
git clone <this repo> neighborhood-server
cd neighborhood-server
make bootstrap
```

`make bootstrap` will:

- Verify Docker, Python, and (if present) Ollama
- Generate `secrets/rcon_password` if missing
- Create `.env` from `.env.example` with a random `AGENT_API_TOKEN`
- Ask whether `/agent` should use host Ollama or the Compose `ollama` profile
- Warn if you haven't pulled `gemma4:12b-mlx` yet (host Mac path)
- If `PLAYIT_SECRET_KEY` is already in `.env`, run `scripts/playit_setup.py`
  for Java + Bedrock tunnels

Playit later:

```bash
echo "PLAYIT_SECRET_KEY=pit-XXXXXXXX..." >> .env
make tunnels
make invite
```

## 2. LLM for `/agent` (pick one)

### Path A — host Ollama (Mac GPU)

```bash
ollama pull gemma4:12b-mlx
# .env: LOCAL_LLM_BASE_URL / OLLAMA_BASE_URL = http://host.docker.internal:11434
make up
```

### Path B — bundled Ollama (Linux/Windows)

```bash
# bootstrap sets OLLAMA_BASE_URL=http://ollama:11434 + COMPOSE_PROFILES=ollama
make up
docker compose logs -f mc-ollama-pull
```

### Path C — non-Mac local instruct model

```bash
ollama pull qwen2.5:7b-instruct
# set LOCAL_LLM_MODEL=qwen2.5:7b-instruct and OLLAMA_MODEL=qwen2.5:7b-instruct in .env
make up
```

Expect slower Tier-B (model) latency; common/fast-path asks stay snappy.

## 3. Wait for the server (first boot only)

```bash
make logs
make status
```

## 4. Plugin + templates

```bash
make plugin
make seed     # one-time; needs an online player
```

## 5. Join (whitelist on by default)

```bash
./mc.sh cmd "whitelist add <your_java_name>"
./mc.sh cmd "whitelist add .<bedrock_gamertag>"   # leading dot for Bedrock
./mc.sh op <your_java_name>                       # optional — kids need not be op
```

Connect at `localhost:25565` (Java) or `localhost:19132` (Bedrock).

## 6. Try `/agent` (sidekick)

No cheats required. Family defaults let every player use `/agent`. Builds
still respect GriefPrevention claims.

```text
/agent make it daytime
/agent give me three dirt blocks
/agent spawn three chickens here
/agent build me a small chicken coop
/agent finish this wall in front of me 8 blocks high
/agent undo that
```

What it **won't** do: dig/clear large areas, admin blocks (command/structure),
bypass someone else's claim, or exceed edit budgets.

## 7. Validate

```bash
make test
make companion-gate                 # offline accuracy + latency
make companion-live                 # needs a player online
make companion-live-dialogue
```

## 8. Tear down

```bash
make down
```

See [HOSTING.md](HOSTING.md) for weekend hosting, [ARCHITECTURE.md](ARCHITECTURE.md)
for how the companion works, and [DEPRECATED.md](DEPRECATED.md) for retired
RCON-orchestrator surfaces.
