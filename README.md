# Neighborhood Minecraft Server

> **Self-hosted, free, crossplay Minecraft server with a magical AI agent
> that runs *locally*.**  Talk to the world in plain English from
> Minecraft chat — `/agent build me a small cabin` — and watch it happen.
> All tools, all builds, all routing run on your own machine. No cloud
> required (but optional cloud fallback is supported).
>
> Status: experimental, working great on a single Mac mini. License: MIT.

## What you get

- A Paper Minecraft server (Java + Bedrock crossplay via Geyser + Floodgate)
- An in-game `/agent <prompt>` command backed by a local LLM (Ollama)
- 60+ typed tools the agent can call — `build_platform`, `build_house_at_player`,
  `fawe_cyl_at_player`, `summon_entity`, etc. — the same registry that drives
  the Cursor MCP integration
- A 101-template `.schem` corpus with hybrid (lexical + semantic + policy)
  ranking so natural prompts ("a place for chickens to live") map to the
  right schematic
- An eval harness (19 strict spec cases, 26 NL smoke prompts, ~612-prompt
  live corpus) that ships with a baseline so regressions show up as PR diffs
- Audit log, Prometheus `/metrics`, deep `/health`, RCON-coordinated backups
- Optional bundled Ollama Compose profile so Linux/Windows users can run the
  whole stack with no host install

## 30-second start

```bash
git clone <this repo> neighborhood-server
cd neighborhood-server
make bootstrap            # secrets, .env + AGENT_API_TOKEN, Ollama path choice
make up                   # boots Paper + agent (+ bundled Ollama if chosen)
make plugin && make seed  # in-game plugin + schematic corpus
./mc.sh op <yourname>     # whitelist is on by default — add yourself first
# /agent build me a hollow stone cylinder around me radius 6
```

`make help` lists every target. Read on for the full setup story, or jump to
[docs/PUBLIC_QUICKSTART.md](docs/PUBLIC_QUICKSTART.md) for the condensed version.

## Stack at a glance

- **Server**: Paper 26.1.2 (Java 25) via [`itzg/minecraft-server`](https://docker-minecraft-server.readthedocs.io/)
- **Crossplay**: GeyserMC + Floodgate (Bedrock players join with their Xbox account)
- **External access**: official `playit-agent` sidecar (free tier covers Java + Bedrock)
- **Backups**: `itzg/mc-backup` sidecar, RCON-coordinated, every 2h, 14-day retention
- **Agent**: FastAPI orchestrator (`mc-agent`) → Ollama (host or bundled) → typed tools → RCON
- **Building plugin**: FastAsyncWorldEdit (FAWE) `2.15.1`

## Why playit.gg (and not something else)?

| Option | Java (TCP) | Bedrock (UDP) | Public friends? | Cost |
| --- | --- | --- | --- | --- |
| **playit.gg** | yes | yes | yes | free tier is fine |
| Tailscale | yes | yes | no — friends must install Tailscale | free for ≤3 users |
| Cloudflare Tunnel | Spectrum only (paid) | no | yes | paid |
| ngrok | yes (paid for raw TCP) | beta | yes | paid for the useful tier |
| Direct port forward | yes | yes | yes | free, but exposes your home IP |

If your players already use Tailscale, that's the highest-quality path
(direct WireGuard, no third-party hop). For random friends, playit.gg wins.

---

## 1. Prerequisites

- Docker Desktop 4.x or Docker Engine + Compose v2
- ~6 GB RAM and ~5 GB disk free (more if you bundle Ollama)
- Python 3.11+ on the host (for `make bootstrap` and the eval/training scripts)
- A local LLM for `/agent`: either [Ollama](https://ollama.com) on the host
  (recommended on Mac Apple Silicon — uses Metal GPU) **or** the bundled
  Compose `ollama` profile. Without either, set `OPENAI_API_KEY` in `.env`
  to fall back to cloud.
- (Optional) A free [playit.gg account](https://playit.gg/login) for public
  crossplay tunnels.

## 2. Bootstrap

```bash
git clone <this repo> neighborhood-server
cd neighborhood-server
make bootstrap
```

`make bootstrap` will:

1. Verify Docker + Python (+ Ollama if installed).
2. Generate `secrets/rcon_password` if missing.
3. Copy `.env.example` → `.env` and inject a random `AGENT_API_TOKEN`.
4. Ask whether `/agent` should hit host Ollama or the Compose `ollama`
   profile. It writes `OLLAMA_BASE_URL` and (for the profile path)
   `COMPOSE_PROFILES=ollama` into `.env` so plain `make up` does the right
   thing.

If you want playit.gg crossplay, add `PLAYIT_SECRET_KEY=pit-...` to `.env`
([signup is free](https://playit.gg/login)).

### LLM paths (pick one)

| Path | Best for | What to do |
| --- | --- | --- |
| **Host Ollama** | macOS (Metal GPU), or you already run Ollama | `ollama pull qwen2.5:7b-instruct`, keep `OLLAMA_BASE_URL=http://host.docker.internal:11434`, `make up` |
| **Bundled Ollama** | Linux/Windows, "zero install" deploys | bootstrap chooses this for you, then `make up` (first boot pulls ~5 GB into the `ollama-models` volume) |
| **Cloud only** | No GPU and no spare RAM | Set `OPENAI_API_KEY` (and optionally `CLOUD_BASE_URL`, `CLOUD_MODEL`) in `.env`. The orchestrator will use cloud when local Ollama is unreachable. |

NVIDIA Linux: add the standard `deploy.resources.reservations.devices`
GPU block to the `ollama` service if you want CUDA. The host-network/host
extra hosts already handle Mac/Windows.

## 3. Start the stack

```bash
make up         # docker compose up -d (includes Ollama if COMPOSE_PROFILES=ollama)
make logs       # tail mc + mc-agent (ctrl-c to detach)
make status     # docker compose ps + /health
```

First boot pulls Paper, downloads Geyser + Floodgate, and generates the
world. Expect ~2-3 minutes before `mc-lan` shows `(healthy)`. You're ready
when you see:

```
[Server thread/INFO]: Done (XX.Xs)! For help, type "help"
[geyser-spigot/INFO] Started Geyser on 0.0.0.0:19132
```

## 4. Install the in-game plugin and seed templates

```bash
make plugin   # builds NeighborhoodAgent.jar and drops it in data/plugins
make seed     # pre-builds all 101 schematics in-world (one-time, ~10 min)
```

`make seed` writes `agent/templates/.seed_manifest.json` so re-runs only
rebuild what changed. You need to be on the server as an opped player while
seeding; the script auto-detects an online player.

## 5. Add yourself (and your friends) as ops

Whitelist is **on** by default in the public repo, so add players before
sharing the playit address:

```bash
./mc.sh op <your_java_name>
./mc.sh op .<your_bedrock_gamertag>      # Bedrock players have a leading dot
./mc.sh cmd "whitelist add <name>"
./mc.sh cmd "whitelist add .<bedrock_gamertag>"
```

For an open friends server (anyone with the address can join), set
`MC_ENFORCE_WHITELIST=false` in `.env` and `docker compose restart mc`.

To pre-op a list of players on every restart, uncomment the `OPS:` block
in `docker-compose.yml`.

## 6. Connect

- **LAN**: `localhost:25565` (Java) or `localhost:19132` (Bedrock) when
  connecting from the host. Other machines on the LAN use `<host-lan-ip>:25565`
  / `:19132`.
- **Public (playit)**: follow [playit setup below](#7-playit-tunnels-for-public-crossplay).

## 7. playit tunnels (for public crossplay)

The `playit` service starts automatically. On first boot it registers with
the secret key from `.env` — you don't need to claim a link manually. Confirm:

```bash
docker compose logs playit
# look for: "agent online"  /  "tunnel ... ready"
```

Then open <https://playit.gg/account/tunnels> and add **two tunnels**:

| Tunnel | Type | Local IP | Local Port | Proxy Protocol |
| --- | --- | --- | --- | --- |
| Java | Minecraft Java | `127.0.0.1` | `25565` | None |
| Bedrock | Minecraft Bedrock | `127.0.0.1` | `19132` | None |

> Why "None"? GeyserMC's playit guide suggests `proxy-protocol-v2` so
> Bedrock players' real IPs are preserved, but enabling it forces *all*
> Bedrock clients to speak proxy protocol — which would break your LAN
> connections. Keep it off unless you stop using LAN.

playit will display two public addresses, e.g.

```
ply.gg:54321                         (Java)
visiting-phone.gl.at.ply.gg:6695     (Bedrock)
```

- **Java friends** connect to the playit Java address.
- **Bedrock friends** add a server with the playit Bedrock host and port.

That's it — no router configuration, no exposing your home IP.

## 8. Day-to-day ops

The repo ships a small admin wrapper, `./mc.sh`, that fronts the most common
RCON and container chores. Run it with no args for the full help.

```bash
./mc.sh op .BedrockPlayer       # bedrock player (note the leading dot)
./mc.sh op SomeJavaPlayer
./mc.sh deop SomeJavaPlayer
./mc.sh list                    # who's online
./mc.sh say "Restart in 5 minutes"
./mc.sh gamemode creative .BedrockPlayer
./mc.sh time set day
./mc.sh kick TrollPlayer "no thanks"
./mc.sh ban TrollPlayer
./mc.sh cmd "weather clear 3000"   # raw RCON for anything not wrapped above
./mc.sh console                    # interactive console (Ctrl-P Ctrl-Q to detach)
./mc.sh logs                       # tail Minecraft server logs
./mc.sh status                     # docker compose ps for all services
./mc.sh backup                     # trigger an immediate world backup
```

Bedrock players join via Floodgate with a `.` prefix on their gamertag —
include the dot when running `op`, `kick`, etc.

If you'd rather drive things by hand:

```bash
docker compose logs -f mc                        # live logs
docker attach mc-lan                             # interactive console
docker exec -i mc-lan rcon-cli list              # one-off RCON
docker compose down                              # graceful stop (announces + saves)
docker compose pull && docker compose up -d      # pull updates and roll forward
```

For party operations (preflight, recovery, post-party cleanup) see
[docs/HOSTING.md](docs/HOSTING.md).

## 9. AI building with Cursor (MCP)

This repo ships a project-local MCP server at `.cursor/mcp.json`:

- MCP name: `minecraft-builder`
- Implementation: `mcp/minecraft_build_mcp.py`
- Transport: stdio via `uv run --script`
- Auth: no RCON password in Cursor config; tools shell into `mc-lan` and use
  the container's built-in `rcon-cli`

After opening this project in Cursor, go to **Cursor Settings -> MCP** and make
sure `minecraft-builder` is enabled. If Cursor was already open before the MCP
file was added, restart Cursor or reload the window.

Example things to ask Cursor:

```text
Use minecraft-builder to list online players.
Use minecraft-builder to build a 21x21 quartz platform at 0 80 0.
Use minecraft-builder to build a hollow glass sphere of radius 10 around 25 90 25.
Use minecraft-builder to build a spiral staircase at 50 70 50.
Use minecraft-builder to teleport .BedrockPlayer to 0 90 0.
Use minecraft-builder to run the raw command time set day.
```

The MCP has guardrails:

- max cuboid size defaults to `200000` blocks
- max generated command count defaults to `20000`
- RCON is not exposed on a host port
- raw commands exist as an escape hatch, but purpose-built build tools are safer

FastAsyncWorldEdit is also installed. The MCP exposes `fawe_as_player` for
commands that need a player context/location/selection, for example running
WorldEdit commands as `.BedrockPlayer`.

### Cursor rules (so new chats just know what to do)

The repo ships project-scoped Cursor rules at `.cursor/rules/`:

- `01-server-overview.mdc` — stack, container names, ports, defaults
- `02-minecraft-tools.mdc` — MCP first, then `mc.sh` / `op.sh`, then raw
  `docker exec`; building patterns and guardrails
- `03-safety.mdc` — secrets, RCON internal-only, JVM-flag pinning,
  whitelist + AGENT_API_TOKEN rules
- `04-in-game-agent.mdc` — `/agent` command, orchestrator, model routing

All four are `alwaysApply: true`, so any new Cursor chat in this workspace
already has the context. You can just say things like:

```text
Build me a 31x31 quartz platform centered at 100 80 -50, hollow walls 4 blocks tall.
Op .NewBedrockPlayer and put them in creative.
Backup now, then run //regen on .BedrockPlayer's selection.
```

## 10. In-game `/agent` (local AI + shared MCP tools)

Type prompts in Minecraft chat — same tool core as the Cursor MCP, routed
through the Compose-managed `mc-agent` orchestrator and local model (Ollama),
with optional cloud fallback.

```text
/agent build a 21x21 quartz platform at my feet
/agent dig a shaft 32 blocks below me
/agent give me haste and set time to day
/agent build a chicken coop in front of me
/agent good                              # rate the previous job good
/agent bad bridge was too high           # rate it bad (training signal)
/agent confirm <token> clear this area   # destructive ops require a token
```

The plugin config (auto-generated in `data/plugins/NeighborhoodAgent/config.yml`)
points at the Compose service:

```yaml
orchestrator-url: http://mc-agent:8787
api-token: env:AGENT_API_TOKEN
job-timeout-seconds: 90
```

**Routing**: local Ollama → bounded local fallback (`OLLAMA_FALLBACK_MODEL`)
→ cloud if `OPENAI_API_KEY` is set. Cloud is third-tier; the live default is
host Ollama.

### Models that work well (2026)

| Tier | Ollama tag | RAM | Notes |
| --- | --- | --- | --- |
| Default | `qwen2.5:7b-instruct` | ~5 GB | Reliable fast path on this host |
| Bounded fallback | `qwen3:8b` | ~5 GB | Smarter in theory; bounded by timeout |
| Baseline | `llama3.1:8b` | ~5.5 GB | Battle-tested, no thinking quirks |
| Step up | `qwen3:14b` / `qwen2.5:14b` | ~9 GB | Better multi-tool reasoning if you have headroom |
| Avoid | MoE / "elastic" tags | — | Multi-step tool chains tend to fragment on routing |

There is no useful Minecraft-specific Ollama model for tool-calling agents.
We make a generalist Minecraft-smart instead via prompt strategies + RAG-lite
(see [docs/FINE_TUNING.md](docs/FINE_TUNING.md) for the training loop).

### Smart context (server-side, every job)

`agent/context.py` pulls a snapshot from your running server and injects it
into the system prompt:

- online players, current time of day, player facing direction
- ground block under the player
- last few `/agent` actions for follow-up prompts ("make it taller")

### Knowledge base (`agent/knowledge/`)

- `blocks.md` — curated Minecraft block IDs by category (stops the model
  from hallucinating `quartz` instead of `quartz_block`)
- `fawe.md` — FastAsyncWorldEdit cheatsheet (`//set`, `//walls`, `//hsphere`,
  selections, brushes, schematics)
- `patterns.md` — recipe library (platform, dome, tower, bunker, mining)

`agent/retrieval.py` keyword-ranks chunks against the prompt and injects the
top matches into context. Edit any `*.md` and restart the orchestrator
(`docker compose restart mc-agent`) to pick up changes.

### Safety

Destructive ops require `/agent confirm <token> ...`. Rate limit, audit log
(`data/agent-audit.log`), RCON denylist. `mc-agent` does not publish ports
to the host or playit; the plugin reaches it on the private Compose network.

### Hybrid template ranker

Natural-language prompts like *"a place for chickens to live"* or *"build a
fortress"* are resolved by `agent/templates/ranking.py` (lexical + local-CPU
semantic + policy reranker → confidence gate) before `paste_template_at_player`
runs. The catalog ships 101 verified `.schem` files; multi-story house,
bridge, and castle builders include real interiors, railings, and stairs by
default. See [docs/TEMPLATE_RANKING.md](docs/TEMPLATE_RANKING.md).

### Agent framework (eval, registry, training prep)

- **Tool contracts** — single registry in `agent/tool_registry.py`
  (schema, dispatch, MCP stay in sync); current `TOOLS_VERSION` is `2.9.0`
- **Validation tiers** — `make test | smoke | eval | live-tools |
  full-validation | corpus-quick | corpus`
- **Auto-detected player** — `scripts/_detect_player.sh` finds an online
  player so `make smoke` and friends Just Work
- **Fine-tuning loop** — `make train` (SFT + DPO export + LoRA dry-run) and
  `make train-full` (full LoRA → GGUF → Ollama register) — see
  [docs/FINE_TUNING.md](docs/FINE_TUNING.md)
- **Feedback capture** — `/agent good|bad` writes to `data/agent-feedback.jsonl`
- **Model comparison** — `make compare-models` (stock qwen2.5 vs trained tag)
- **More docs** — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
  [docs/TOOL_CONTRACT.md](docs/TOOL_CONTRACT.md),
  [docs/DEVELOPMENT_WORKFLOW.md](docs/DEVELOPMENT_WORKFLOW.md),
  [docs/HOSTING.md](docs/HOSTING.md), [CONTRIBUTING.md](CONTRIBUTING.md)

## 11. Backups

`./backups/` fills automatically every 2 hours; old archives are pruned
after 14 days. Restore:

```bash
docker compose stop mc
mv data/world data/world.bad
tar -xzf backups/world-YYYY-MM-DD-HH-MM-SS.tgz -C data/
docker compose start mc
```

## 12. Updating Minecraft version

When Mojang ships a new version supported by Paper:

1. Edit `docker-compose.yml`, change `VERSION:` (e.g. `"26.2.0"`).
2. Make sure you have a fresh backup in `./backups/`.
3. `docker compose pull && docker compose up -d`.

If a major version requires a newer Java, also bump
`image: itzg/minecraft-server:javaXX` per the
[Paper Java requirements](https://docs.papermc.io/paper/getting-started/).

## 13. Troubleshooting

- **`Compose refuses to start: AGENT_API_TOKEN is required`** — Either run
  `make bootstrap` to generate one, or paste a long random string into
  `.env` (`AGENT_API_TOKEN=...`).
- **`/agent` says "Agent misconfigured"** — same root cause; `AGENT_API_TOKEN`
  is missing from the container env. Restart after fixing.
- **`/agent` says "Agent offline"** — `make health` or
  `docker compose logs mc-agent`. If you chose the bundled Ollama profile,
  also check `docker compose logs mc-ollama`.
- **Bundled Ollama first boot is slow** — it's pulling the ~5 GB model into
  the `ollama-models` volume. `docker compose logs mc-ollama-pull` shows
  progress.
- **Container restart loop with "fabric" / "modrinth" errors** — leftover
  files from a previous Fabric attempt. `docker compose down`, delete
  `data/.install-fabric.env`, `data/.fabric-manifest.json`, any
  `data/fabric-server-*.jar`, and `data/mods/`, then `docker compose up -d`.
- **"Done" never appears** — first boot is slow because plugins download.
  Watch `docker compose logs -f mc`. If it actually hangs, set
  `DEBUG: "true"` in the `mc` service environment and re-run.
- **Bedrock can't connect on LAN** — make sure UDP `19132` is published
  (`docker compose port mc 19132/udp`) and that no other process owns it
  (`lsof -nP -iUDP:19132`).
- **playit shows "agent offline"** — `PLAYIT_SECRET_KEY` is wrong or the
  host has no internet egress. Re-issue a secret in the playit dashboard
  and update `.env`.
- **Bedrock friend can't join via playit** — confirm the tunnel type is
  *Minecraft Bedrock* (not custom UDP) and that *Proxy Protocol* is *None*.

## File layout

```
neighborhood-server/
├── docker-compose.yml          # mc + mc-agent + playit + backup (+ ollama profile)
├── Makefile                    # one-liner targets — `make help`
├── README.md                   # this file
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── .env.example                # template; `make bootstrap` produces .env
├── .gitignore / .dockerignore
├── agent/                      # Python: orchestrator, tools, registry, eval, templates, training
│   ├── orchestrator/app.py     # FastAPI app (runs as mc-agent)
│   ├── tools/                  # admin, builders, fawe, inspection, templates
│   ├── tool_registry.py        # single source of truth (TOOLS_VERSION)
│   ├── templates/
│   │   ├── catalog.json
│   │   └── schematics/*.schem  # 101 verified
│   ├── knowledge/*.md          # blocks / fawe / patterns RAG-lite
│   └── eval/                   # spec + corpus eval harness
├── plugins/neighborhood-agent/ # Paper /agent plugin source (Java)
├── mcp/minecraft_build_mcp.py  # Cursor MCP adapter
├── mc.sh, op.sh                # RCON / admin wrappers
├── scripts/                    # bootstrap, build-plugin, agent-smoke, eval, seed, etc.
├── tests/                      # 170+ unit / contract tests
├── docs/                       # ARCHITECTURE, TOOL_CONTRACT, HOSTING, CORPUS, ...
├── .cursor/                    # mcp.json + rules (alwaysApply)
├── secrets/rcon_password       # gitignored
├── .env                        # gitignored
├── data/                       # world + plugins (gitignored)
└── backups/                    # mc-backup output (gitignored)
```
