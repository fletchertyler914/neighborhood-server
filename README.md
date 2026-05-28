# Neighborhood Minecraft Server

A self-hosted, crossplay Minecraft server (Java + Bedrock) you can run on any
machine with Docker. LAN access works out of the box. External access uses
[playit.gg](https://playit.gg) so you never touch your router.

- **Server**: Paper 26.1.2 (Java 25) via [`itzg/minecraft-server`](https://docker-minecraft-server.readthedocs.io/)
- **Crossplay**: GeyserMC + Floodgate (Bedrock players join with their Xbox account)
- **External access**: official `playit-agent` sidecar (free tier supports Java + Bedrock)
- **Backups**: `itzg/mc-backup` sidecar, RCON-coordinated, every 2h, 14-day retention

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
- ~5 GB RAM and ~5 GB disk free
- A [playit.gg account](https://playit.gg/login) (free)

## 2. First-time setup

```bash
git clone <this repo> neighborhood-server
cd neighborhood-server
```

### 2a. Create the RCON password secret

```bash
mkdir -p secrets
openssl rand -hex 32 > secrets/rcon_password
chmod 600 secrets/rcon_password
```

This file is referenced by Compose via Docker secrets and is **not**
committed (see `.gitignore`).

### 2b. Get a playit.gg secret key

1. Open <https://playit.gg/account/setup/wizard/new-account/docker/docker-name>.
2. Sign in, give the agent a name (e.g. `neighborhood-server`), and copy the
   secret key it generates.
3. Save it to a local `.env` file:

   ```bash
   echo 'PLAYIT_SECRET_KEY=pit-...' > .env
   chmod 600 .env
   ```

`.env` is also gitignored.

### 2c. (Optional) Add yourself as op and whitelist your players

Edit `docker-compose.yml` and fill in `OPS:` and `WHITELIST:` (one player
name per line). The image resolves names to UUIDs automatically.

## 3. Start the server

```bash
docker compose up -d
```

First boot pulls Paper, downloads Geyser + Floodgate, and generates the
world. Expect ~2–3 minutes before the container reports healthy.

Watch progress:

```bash
docker compose logs -f mc
```

You're ready when you see:

```
[Server thread/INFO]: Done (XX.Xs)! For help, type "help"
[geyser-spigot/INFO] Started Geyser on 0.0.0.0:19132
```

Confirm health:

```bash
docker compose ps
# mc should show (healthy)
```

## 4. Connect from LAN

Find the host machine's LAN IP (e.g. `192.168.1.42`).

- **Java Edition** → *Add Server* → `192.168.1.42:25565`
- **Bedrock Edition** (Win/iOS/Android/console) → *Servers* → *Add Server*
  → IP `192.168.1.42`, Port `19132`

Players on the same machine can use `localhost` instead.

## 5. Set up the playit.gg tunnels (one-time)

The `playit` service is already started by `docker compose up`. On first run
the agent registers itself with the secret key from `.env` — you don't need
to claim a link manually. Confirm:

```bash
docker compose logs playit
# look for: "agent online"  /  "tunnel ... ready"
```

Then open <https://playit.gg/account/tunnels> and add **two tunnels**:

### Java tunnel

- *Tunnel Type*: **Minecraft Java**
- *Local IP*: `127.0.0.1`
- *Local Port*: `25565`
- *Proxy Protocol*: **None**

### Bedrock tunnel

- *Tunnel Type*: **Minecraft Bedrock**
- *Local IP*: `127.0.0.1`
- *Local Port*: `19132`
- *Proxy Protocol*: **None**

> Why "None"? GeyserMC's playit guide suggests `proxy-protocol-v2` so
> Bedrock players' real IPs are preserved, but enabling it forces *all*
> Bedrock clients to speak proxy protocol — which would break your LAN
> connections. Keep it off unless you stop using LAN.

playit will display two public addresses, e.g.

```
ply.gg:54321         (Java)
visiting-phone.gl.at.ply.gg:6695   (Bedrock)
```

## 6. Share with external players

- **Java friends** connect to the playit Java address, e.g. `ply.gg:54321`.
- **Bedrock friends** add a server with the playit Bedrock host and port.

That's it — no router configuration, no exposing your home IP.

## 7. Day-to-day ops

The repo ships a small admin wrapper, `./mc.sh`, that fronts the most common
RCON and container chores. Run it with no args for the full help.

```bash
./mc.sh op .LunarLicense582       # bedrock player (note the leading dot)
./mc.sh op SomeJavaPlayer
./mc.sh deop SomeJavaPlayer
./mc.sh list                      # who's online
./mc.sh say "Restart in 5 minutes"
./mc.sh gamemode creative .LunarLicense582
./mc.sh time set day
./mc.sh kick TrollPlayer "no thanks"
./mc.sh ban TrollPlayer
./mc.sh cmd "weather clear 3000"  # raw RCON for anything not wrapped above
./mc.sh console                   # interactive console (Ctrl-P Ctrl-Q to detach)
./mc.sh logs                      # tail Minecraft server logs
./mc.sh status                    # docker compose ps for all services
./mc.sh backup                    # trigger an immediate world backup
```

Bedrock players join via Floodgate with a `.` prefix on their gamertag —
include the dot when running `op`, `kick`, etc.

If you'd rather drive things by hand:

```bash
docker compose logs -f mc                 # live logs
docker attach mc-lan                      # interactive console
docker exec -i mc-lan rcon-cli list       # one-off RCON
docker compose down                       # graceful stop (announces + saves)
docker compose pull && docker compose up -d   # pull updates and roll forward
```

### AI building with Cursor MCP

This repo includes a project-local MCP server at `.cursor/mcp.json`:

- MCP name: `minecraft-builder`
- implementation: `mcp/minecraft_build_mcp.py`
- transport: stdio via `uv run --script`
- auth: no RCON password in Cursor config; tools shell into `mc-lan` and use
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
Use minecraft-builder to teleport .LunarLicense582 to 0 90 0.
Use minecraft-builder to run the raw command time set day.
```

The MCP has guardrails:

- max cuboid size defaults to `200000` blocks
- max generated command count defaults to `20000`
- RCON is not exposed on a host port
- raw commands exist as an escape hatch, but purpose-built build tools are safer

FastAsyncWorldEdit is also installed. The MCP exposes `fawe_as_player` for
commands that need a player context/location/selection, for example running
WorldEdit commands as `.LunarLicense582`.

#### Cursor rules (so new chats just know what to do)

This repo also ships project-scoped Cursor rules at `.cursor/rules/`:

- `01-server-overview.mdc` — the stack, container names, ports, defaults
- `02-minecraft-tools.mdc` — `minecraft-builder` MCP first, then `mc.sh` /
  `op.sh`, then raw `docker exec`; building patterns and guardrails
- `03-safety.mdc` — secrets, RCON-internal-only, JVM-flag pinning,
  whitelist/public-exposure rules
- `04-in-game-agent.mdc` — `/agent` command, orchestrator, model routing

All four are `alwaysApply: true`, so any new Cursor chat opened in this
workspace already has the context. You can just say things like:

```text
Build me a 31x31 quartz platform centered at 100 80 -50, hollow walls 4 blocks tall.
Op .NewBedrockPlayer and put them in creative.
Backup now, then run //regen on .LunarLicense582's selection.
```

### In-game `/agent` (local AI + shared MCP tools)

Type prompts in Minecraft chat — same tool core as Cursor MCP, routed through the
Compose-managed `mc-agent` orchestrator and local model (Ollama), with optional
cloud fallback.

```text
/agent build a 21x21 quartz platform at my feet
/agent dig a shaft 32 blocks below me
/agent give me haste and set time to day
/agent confirm <token> clear this area   # after destructive-action prompt
```

**One-time setup**

1. Copy agent vars from `.env.example` into `.env` and set `AGENT_API_TOKEN`.
2. Install [Ollama](https://ollama.com) on the host and pull the local models:
   `ollama pull qwen2.5:7b-instruct && ollama pull qwen3:8b`
3. Build and install the Paper plugin:
   `./scripts/build-plugin.sh`
4. Start the whole stack:
   `docker compose up -d --build`

The plugin config should point to the Compose service:

```yaml
orchestrator-url: http://mc-agent:8787
api-token: env:AGENT_API_TOKEN
```

**Hybrid models:** local Ollama is tried first. If it fails and `OPENAI_API_KEY`
is set, the orchestrator falls back to `CLOUD_MODEL` (OpenAI-compatible API).

**Models that work well (2026):**

| Tier | Ollama tag | RAM | Notes |
| --- | --- | --- | --- |
| Default | `qwen2.5:7b-instruct` | ~5 GB | Reliable fast path on this host. |
| Bounded fallback | `qwen3:8b` | ~5 GB | Smarter in theory, but can load slowly; the orchestrator caps local model timeouts. |
| Baseline | `llama3.1:8b` | ~5.5 GB | Battle-tested, no thinking quirks. |
| Step up | `qwen3:14b` / `qwen2.5:14b` | ~9 GB | Better complex multi-tool prompts if your Mac has headroom. |
| Avoid | MoE / "elastic" tags | — | Multi-step tool chains tend to fragment on routing. |

There is no useful Minecraft-specific Ollama model for tool-calling agents.
We make a generalist Minecraft-smart instead via prompt strategies + RAG-lite
(see below).

**Smart context (server-side, every job):** the orchestrator pulls a fast
snapshot from your running server and injects it into the system prompt:

- online players, current time of day, player facing direction
- ground block under the player
- last few `/agent` actions for follow-up prompts ("make it taller")

**Knowledge base (`agent/knowledge/`):**

- `blocks.md` — curated Minecraft block IDs by category (stops the model
  from hallucinating `quartz` instead of `quartz_block`)
- `fawe.md` — FastAsyncWorldEdit cheatsheet (`//set`, `//walls`, `//hsphere`,
  selections, brushes, schematics)
- `patterns.md` — recipe library (platform, dome, tower, bunker, mining)

`agent/retrieval.py` keyword-ranks chunks against the prompt and injects the
top matches into context — full embedding RAG was overkill for our footprint.
Edit any `*.md` and restart the orchestrator to update.

**Safety:** destructive ops require `/agent confirm <token> ...`. Rate limit,
audit log (`data/agent-audit.log`), RCON denylist. `mc-agent` does not publish
ports to the host or playit; the plugin reaches it on the private Compose network.

**Magic tools** (orchestrator + MCP): `build_platform`, `build_sphere`,
`fawe_sphere_at_player`, `mine_shaft_at_player`, `give_haste`, `backup_now`.

**Hybrid template ranker.** Natural-language prompts like *"a place for
chickens to live"* or *"build a fortress"* are resolved by
`agent/templates/ranking.py` (lexical + local-CPU semantic + policy
reranker → confidence gate) before `paste_template_at_player` runs. The
catalog ships 101 verified `.schem` files; multi-story house, bridge,
and castle builders include real interiors, railings, and stairs by
default. See [docs/TEMPLATE_RANKING.md](docs/TEMPLATE_RANKING.md) for
details, weights, and the latest production-validation snapshot.

**Agent framework** (eval, registry, training prep):

- Tool contracts: single registry in `agent/tool_registry.py` (schema, dispatch, MCP stay in sync)
- Kitchen-sink dev loop: [docs/DEVELOPMENT_WORKFLOW.md](docs/DEVELOPMENT_WORKFLOW.md)
- Tool integration: `AGENT_LIVE_TOOL_PLAYER=firecrab93 ./scripts/live-tool-tests.sh` directly executes tools on Paper and probes blocks with RCON
- One-command validation: `./scripts/validate-all.sh` (add `RUN_LIVE=1` / `RUN_FULL_WORLD=1` for live gates)
- Real `/agent` NL smoke: `AGENT_SMOKE_PLAYER=firecrab93 ./scripts/agent-smoke.sh`
- Eval harness: `./scripts/eval.sh spec` (live dry-run) and `./scripts/eval.sh world` (sandbox mutations)
- Export: `./scripts/export-dataset.sh` → JSONL for review / fine-tuning
- Feedback training data: `python3 -m agent.training feedback --sft-out ... --dpo-out ...`
- Compare models: `AGENT_COMPARE_MODELS=... ./scripts/compare-models.sh`
- Docs: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/TOOL_CONTRACT.md](docs/TOOL_CONTRACT.md), [CONTRIBUTING.md](CONTRIBUTING.md)

### Backups

`./backups/` fills automatically every 2 hours; old archives are pruned
after 14 days. Restore:

```bash
docker compose down
tar -xzf backups/world-2026-05-27-12-00-00.tgz -C data/
docker compose up -d
```

## 8. Updating Minecraft version

When Mojang ships a new version supported by Paper:

1. Edit `docker-compose.yml`, change `VERSION:` (e.g. `"26.2.0"`).
2. Make sure you have a fresh backup in `./backups/`.
3. `docker compose pull && docker compose up -d`.

If a major version requires a newer Java, also bump
`image: itzg/minecraft-server:javaXX` per the
[Paper Java requirements](https://docs.papermc.io/paper/getting-started/).

## 9. Troubleshooting

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
├── docker-compose.yml      # Paper + Geyser/Floodgate + playit + backups
├── agent/                  # orchestrator, tools, eval harness, training stubs
├── docs/                   # ARCHITECTURE.md, TOOL_CONTRACT.md
├── README.md               # this file
├── .env                    # PLAYIT_SECRET_KEY=...   (gitignored)
├── .gitignore
├── secrets/
│   └── rcon_password       # gitignored
├── data/                   # world + plugins (gitignored)
└── backups/                # mc-backup output (gitignored)
```
