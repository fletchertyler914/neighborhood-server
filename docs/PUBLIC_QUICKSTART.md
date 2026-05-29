# Public quickstart

This is the new-clone, get-running-fast guide. For the deeper setup story
(playit.gg crossplay, ops/whitelist, backups), see the main [README](../README.md).

## Prerequisites

- Docker Desktop (macOS / Windows) or Docker Engine + Compose v2 (Linux)
- Python 3.11 or newer
- ~6 GB free RAM, ~5 GB free disk
- A local LLM for `/agent`: either [Ollama](https://ollama.com) on the host
  (recommended on Mac for GPU) **or** the bundled Compose `ollama` profile
  (no host install). Without either, set `OPENAI_API_KEY` in `.env`.

## 1. Bootstrap

```bash
git clone <this repo> neighborhood-server
cd neighborhood-server
make bootstrap
```

`make bootstrap` will:

- Verify Docker, Python, and (if present) Ollama
- Generate a fresh RCON password into `secrets/rcon_password`
- Create `.env` from `.env.example` with a randomly-generated `AGENT_API_TOKEN`
- Pick host Ollama vs the Compose `ollama` profile (interactive if no host Ollama)
- Warn if you haven't pulled `qwen2.5:7b-instruct` yet (host path only)

If you want playit.gg crossplay tunnels, add a `PLAYIT_SECRET_KEY` to `.env`
([signup is free](https://playit.gg/login)).

## 2. LLM for `/agent` (pick one path)

### Path A — host Ollama (Mac GPU, or you already use Ollama)

```bash
ollama pull qwen2.5:7b-instruct
# .env should have OLLAMA_BASE_URL=http://host.docker.internal:11434 (bootstrap sets this)
make up
```

### Path B — bundled Ollama (Linux/Windows, zero host install)

```bash
# bootstrap sets OLLAMA_BASE_URL=http://ollama:11434
docker compose --profile ollama up -d   # first run pulls the model (~5 GB)
```

The orchestrator falls back to `qwen3:8b` if the primary stalls, and to
OpenAI if `OPENAI_API_KEY` is set.

## 3. Start the stack (if not already up)

```bash
make up         # host-Ollama path (docker compose up -d)
make logs       # watch first boot (ctrl-c to detach)
```

First boot takes ~2-3 minutes (Paper download + plugin install + world gen).
You're ready when `mc-lan` shows `(healthy)` in `make status`.

## 4. Build the in-game plugin and seed templates

```bash
make plugin     # builds the NeighborhoodAgent JAR and copies it into data/plugins
make seed       # runs the deterministic seeder; pre-builds all 101 .schem files in-world
```

`make seed` writes a `agent/templates/.seed_manifest.json` so re-runs only
rebuild what changed.

## 5. Join and try it

Connect at `localhost:25565` (Java) or `localhost:19132` (Bedrock).

Whitelist is **on** by default. Add yourself before guests join:

```bash
./mc.sh cmd "whitelist add <your_java_name>"
./mc.sh cmd "whitelist add .<bedrock_gamertag>"   # leading dot for Bedrock
```

Friends-server mode (anyone with the playit address can join): set
`MC_ENFORCE_WHITELIST=false` in `.env` and restart `mc`.

In Minecraft chat:

```text
/agent build me a small cabin in front of me
/agent give me haste and set time to day
/agent build a hollow stone brick cylinder around me radius 6 height 8
/agent good                          # mark the last response as a good example
/agent confirm <token> clear ...     # destructive ops require a confirm token
```

## 6. Validate

```bash
make test           # 129+ fast unit / contract tests
make smoke          # 26 NL prompts → live LLM → orchestrator (needs you online)
make eval           # 19-case strict spec eval vs baseline
make live-tools     # RCON-level tool integration tests
```

## 7. Tear down

```bash
make down                  # stop containers, keep world
docker compose down -v     # also wipe data/ — be sure
```

See [DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md) for the full
training-data + fine-tuning loop, and [ARCHITECTURE.md](ARCHITECTURE.md)
for how the pieces fit together.
