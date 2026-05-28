# Public quickstart

This is the new-clone, get-running-fast guide. For the deeper setup story
(playit.gg crossplay, ops/whitelist, backups), see the main [README](../README.md).

## Prerequisites

- Docker Desktop (macOS / Windows) or Docker Engine + Compose v2 (Linux)
- Python 3.11 or newer
- ~6 GB free RAM, ~5 GB free disk
- (Optional but recommended) [Ollama](https://ollama.com) on the host for
  free, local LLM inference. Without Ollama you can fall back to OpenAI by
  setting `OPENAI_API_KEY` in `.env`.

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
- Warn if you haven't pulled `qwen2.5:7b-instruct` yet

If you want playit.gg crossplay tunnels, add a `PLAYIT_SECRET_KEY` to `.env`
([signup is free](https://playit.gg/login)).

## 2. Pull a model (recommended)

```bash
ollama pull qwen2.5:7b-instruct
```

This is the default local model. The orchestrator falls back to
`qwen3:8b` if the primary stalls, and to OpenAI if `OPENAI_API_KEY` is set.

## 3. Start the stack

```bash
make up         # equivalent to docker compose up -d
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
