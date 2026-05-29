# Public quickstart

The condensed "fresh clone to playing" path. For the full setup story
(playit.gg crossplay, ops/whitelist details, Cursor MCP, backups), see the
main [README](../README.md).

## Prerequisites

- Docker Desktop (macOS / Windows) or Docker Engine + Compose v2 (Linux)
- Python 3.11 or newer (for `make bootstrap` and the eval/training scripts)
- ~6 GB free RAM, ~5 GB free disk
- A local LLM for `/agent`: either [Ollama](https://ollama.com) on the host
  (recommended on Mac for Metal GPU) **or** the bundled Compose `ollama`
  profile (no host install). Without either, set `OPENAI_API_KEY` in `.env`
  for cloud fallback.

## 1. Bootstrap

```bash
git clone <this repo> neighborhood-server
cd neighborhood-server
make bootstrap
```

`make bootstrap` will:

- Verify Docker, Python, and (if present) Ollama
- Generate `secrets/rcon_password` if missing
- Create `.env` from `.env.example` with a randomly-generated `AGENT_API_TOKEN`
- Ask whether `/agent` should use host Ollama or the Compose `ollama` profile
  and write `OLLAMA_BASE_URL` (plus `COMPOSE_PROFILES=ollama` for the bundled
  path) so plain `make up` does the right thing
- Warn if you haven't pulled `qwen2.5:7b-instruct` yet (host path only)

If you want playit.gg crossplay tunnels, add `PLAYIT_SECRET_KEY=pit-...` to
`.env` ([signup is free](https://playit.gg/login)).

## 2. LLM for `/agent` (pick one path)

### Path A — host Ollama (Mac GPU, or you already use Ollama)

```bash
ollama pull qwen2.5:7b-instruct
ollama pull qwen3:8b              # optional fallback
# .env: OLLAMA_BASE_URL=http://host.docker.internal:11434 (bootstrap sets this)
make up
```

### Path B — bundled Ollama (Linux/Windows, zero host install)

```bash
# .env: OLLAMA_BASE_URL=http://ollama:11434 + COMPOSE_PROFILES=ollama
#       (bootstrap sets both when you pick this path)
make up                           # first boot pulls the model (~5 GB)
docker compose logs -f mc-ollama-pull   # watch the initial pull
```

### Path C — cloud only

```bash
# .env: OPENAI_API_KEY=sk-...   (and optionally CLOUD_BASE_URL, CLOUD_MODEL)
make up
```

The orchestrator always tries local Ollama first, then falls back to
`qwen3:8b` (or whatever `OLLAMA_FALLBACK_MODEL` is set to), then to cloud
if `OPENAI_API_KEY` is present.

## 3. Wait for the server (first boot only)

```bash
make logs       # watch first boot (ctrl-c to detach)
make status     # mc-lan should reach (healthy) in ~2-3 minutes
```

## 4. Build the in-game plugin and seed templates

```bash
make plugin     # builds NeighborhoodAgent.jar and copies it into data/plugins
make seed       # pre-builds all 101 .schem files in-world (one-time, ~10 min)
```

`make seed` writes `agent/templates/.seed_manifest.json` so re-runs only
rebuild what changed. You need an opped player online while seeding; the
script auto-detects one.

## 5. Op yourself, then join

Whitelist is **on** by default. Add yourself and any guests before sharing
the playit address:

```bash
./mc.sh op <your_java_name>
./mc.sh op .<your_bedrock_gamertag>          # Bedrock has a leading dot
./mc.sh cmd "whitelist add <your_java_name>"
./mc.sh cmd "whitelist add .<bedrock_gamertag>"
```

Friends-server mode (anyone with the address can join): set
`MC_ENFORCE_WHITELIST=false` in `.env` and `docker compose restart mc`.

Connect at `localhost:25565` (Java) or `localhost:19132` (Bedrock). For
public access via playit, see the [main README §7](../README.md#7-playit-tunnels-for-public-crossplay).

## 6. Try `/agent`

In Minecraft chat:

```text
/agent build me a small cabin in front of me
/agent give me haste and set time to day
/agent build a hollow stone brick cylinder around me radius 6 height 8
/agent build a chicken coop in front of me
/agent good                          # mark the last response as a training-positive
/agent bad <reason>                  # mark it negative (DPO signal)
/agent confirm <token> clear ...     # destructive ops require a confirm token
```

## 7. Validate

```bash
make test           # 170+ fast unit / contract tests, no live server
make smoke          # 26 NL prompts → live LLM → orchestrator (needs you online)
make eval           # 19-case strict spec eval vs baseline
make live-tools     # RCON-level tool integration tests
make full-validation   # paste every catalog template + summon every supported mob
```

## 8. Tear down

```bash
make down                  # stop containers, keep world
docker compose down -v     # also wipe Docker volumes (incl. ollama-models) — be sure
```

To wipe the world entirely, `make down` then move `data/world*` aside before
the next `make up`.

---

See [DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md) for the training-data
+ fine-tuning loop, [ARCHITECTURE.md](ARCHITECTURE.md) for how the pieces
fit together, and [HOSTING.md](HOSTING.md) for live-party operations.
