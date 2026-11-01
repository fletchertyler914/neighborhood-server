# Neighborhood Minecraft Server

> **Self-hosted, free, crossplay Minecraft with a local AI helper (Crafter).**
> Kids and friends type plain English in chat — `/ai` or `/agent`,
> e.g. `/ai build me a small chicken coop` — and the Paper plugin does it
> natively. Inference stays on your machine (Ollama). No cloud required.
>
> Status: supervised family / home-server beta. License: MIT.

## What you get

- A Paper Minecraft server (Java + Bedrock crossplay via Geyser + Floodgate)
- An in-game `/ai` or `/agent` **helper** (chat name `Crafter`; local LLM + deterministic fast paths)
- Native typed actions over a private WebSocket (`mc-agent` ↔ Paper plugin) —
  **RCON is not used for `/agent`**
- 101 curated `.schem` templates with hybrid lexical + local BoW semantic ranking for natural build asks
- Companion gates: `make companion-gate` (offline) and `make companion-live`
  (world e2e with a player online)
- Sidekick triage: `make companion-feedback-export` / `make companion-triage`
  for the weekly feedback→corpus loop; `make metrics` for live counters
- Audit log, Prometheus `/metrics`, deep `/health`, RCON-coordinated backups
- Optional bundled Ollama Compose profile for Linux/Windows hosts

### What `/agent` can do today

Kid-friendly phrase catalog: [docs/AGENT_PLAYBOOK.md](docs/AGENT_PLAYBOOK.md).

Time/weather, give ordinary items (not admin blocks), summon spawnable mobs,
paste gold-curated templates, finish a visible wall opening, and make bounded
player-relative shapes: walls, platforms, hollow/solid boxes, and cylinders.
“Watchtower” uses a gold template; “tower 10 tall” makes a simple shape. Every
build uses a bounded FAWE changeset, is claim-checked, verified, undoable, and
supports short revisions such as “make it taller” or “use oak.” It does **not**
dig, clear large areas, use FAVS/heightmaps, or run arbitrary WorldEdit.

## 30-second start

```bash
git clone <this repo> neighborhood-server
cd neighborhood-server
make bootstrap            # secrets, .env + AGENT_API_TOKEN, Ollama path choice
# Mac: ollama pull gemma4:12b-mlx
make up                   # boots Paper + companion (+ bundled Ollama if chosen)
make plugin && make seed  # in-game plugin + schematic corpus
./mc.sh cmd "whitelist add <yourname>"
./mc.sh op <yourname>     # optional; kids do not need op for /agent or /ai
# /ai build me a small chicken coop
```

`make help` lists every target. Condensed path:
[docs/PUBLIC_QUICKSTART.md](docs/PUBLIC_QUICKSTART.md). Party ops:
[docs/HOSTING.md](docs/HOSTING.md).

## Stack at a glance

- **Server**: Paper 26.1.2 (Java 25) via [`itzg/minecraft-server`](https://docker-minecraft-server.readthedocs.io/)
- **Crossplay**: GeyserMC + Floodgate (Bedrock players join with their Xbox account)
- **External access**: official `playit-agent` sidecar (free tier covers Java + Bedrock)
- **Backups**: `itzg/mc-backup` sidecar, RCON-coordinated, every 2h, 14-day retention
- **Sidekick**: FastAPI companion (`mc-agent`) → Ollama → typed actions →
  native Bukkit/FAWE execution in the Paper plugin (WebSocket gateway)
- **Building plugin**: FastAsyncWorldEdit (FAWE) `2.15.x`
- **Build protection**: GriefPrevention player claims (sidekick honors claims)
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
- A local LLM for `/agent`: [Ollama](https://ollama.com) on the host
  (recommended on Mac Apple Silicon — `gemma4:12b-mlx` for Metal/MLX) **or**
  the bundled Compose `ollama` profile. There is no cloud fallback in the
  greenfield companion.
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
| **Host Ollama** | macOS Apple Silicon (Metal / MLX) | `ollama pull gemma4:12b-mlx`, `LOCAL_LLM_BASE_URL=http://host.docker.internal:11434`, `make up` |
| **Bundled Ollama** | Linux/Windows, zero host install | bootstrap can set `COMPOSE_PROFILES=ollama`; first boot pulls the model into `ollama-models` |
| **Non-Mac local fallback** | No MLX | e.g. `qwen2.5:7b-instruct` — works, but expect slower Tier-B (model) latency; common/fast-path asks stay snappy |

There is **no cloud LLM path** for the sidekick. NVIDIA Linux: add a Compose
GPU reservation on the `ollama` service if you want CUDA.

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

`PLAYIT_SECRET_KEY` is the only thing playit needs from you — once it's in
`.env`, the rest is automated:

```bash
# One-time agent registration (browser, free):
#   https://playit.gg/account/agents → "Download for Docker" → copy the key
echo "PLAYIT_SECRET_KEY=pit-XXXXXXXX..." >> .env

# Auto-create the standard Java + Bedrock tunnels via the playit API:
make tunnels

# Generate a printable invite sheet with the resulting addresses:
make invite          # writes ~/Desktop/neighborhood-invite.html
```

`make bootstrap` runs `make tunnels` for you automatically when it detects a
secret in `.env`, so a fresh clone with the secret in place needs no manual
playit dashboard work. The script is idempotent — it leaves existing tunnels
alone and only creates what's missing.

The tunnels are created as:

| Tunnel | Type | Local IP | Local Port | Proxy Protocol |
| --- | --- | --- | --- | --- |
| Java | Minecraft Java | `127.0.0.1` | `25565` | None |
| Bedrock | Minecraft Bedrock | `127.0.0.1` | `19132` | None |

> Why "None"? GeyserMC's playit guide suggests `proxy-protocol-v2` so
> Bedrock players' real IPs are preserved, but enabling it forces *all*
> Bedrock clients to speak proxy protocol — which would break your LAN
> connections. Keep it off unless you stop using LAN.

Confirm the agent is online with:

```bash
docker compose logs playit
# look for: "agent online"  /  "tunnel ... ready"
```

playit will assign two public addresses, e.g.

```
regular-nbc.gl.joinmc.link                (Java)
levels-tartly.gl.at.ply.gg:4116           (Bedrock)
```

- **Java friends** connect to the Java address.
- **Bedrock friends** add a server with the Bedrock host and port.

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

## 9. Host operations

The AI sidekick has no external AI-control interface. Server operators use the
auditable shell wrappers for maintenance:

```bash
./mc.sh status
./mc.sh list
./mc.sh backup
./mc.sh op <player>
./mc.sh cmd "<explicit server command>"
```

RCON remains private and is not used by `/agent`.

### Cursor rules

The repo ships project-scoped Cursor rules at `.cursor/rules/`:

- `01-server-overview.mdc` — stack, container names, ports, defaults
- `02-minecraft-tools.mdc` — host scripts, native sidekick boundaries, and
  world-edit guardrails
- `03-safety.mdc` — secrets, RCON internal-only, JVM-flag pinning,
  whitelist + AGENT_API_TOKEN rules
- `04-in-game-agent.mdc` — `/agent` sidekick, companion runtime, validation

All four are `alwaysApply: true`, so any new Cursor chat in this workspace
already has the context.

## 10. In-game `/ai` / `/agent` helper (Crafter)

Players talk to Crafter only through Minecraft chat (no cheats required;
family defaults grant `/agent` and its `/ai` alias to all players). The Paper
plugin maintains an authenticated outbound WebSocket to the private `mc-agent`
runtime. Common requests use deterministic routing; ambiguous requests use one
bounded local-model compile. The plugin revalidates and executes every action
through Bukkit or FAWE APIs and honors GriefPrevention claims.

```text
/ai make it daytime
/agent give me three dirt blocks
/ai spawn three chickens here
/agent build me a small chicken coop
/ai finish this wall in front of me 8 blocks high
/agent undo that
```

The plugin config (auto-generated in `data/plugins/NeighborhoodAgent/config.yml`)
points at the Compose service. Chat label / boss-bar name is `display-name`
(default `Crafter` — change that one string to rename):

```yaml
gateway-url: ws://mc-agent:8787/v1/gateway
api-token: env:AGENT_API_TOKEN
server-id: neighborhood
display-name: Crafter
```

**Model**: `gemma4:12b-mlx` through Ollama (Metal/MLX on Apple Silicon).
Constrained structured output; no cloud cascade.

### Validation / release checklist

```bash
make companion-gate              # offline accuracy + latency floors
make companion-live              # world e2e (needs an online player)
make companion-live-dialogue     # compound + multi-turn clarifies
make companion-triage            # weekly feedback buckets → corpus next steps
```

Weekly loop (export → bucket → seed/alias fix → gate): see
[evals/CORPUS_SOURCES.md](evals/CORPUS_SOURCES.md#weekly-feedback--corpus-loop).

Honest SLOs on a warm Mac Mini-class host: common asks ≤500ms; builds
~0.2–2s; model path ~3–6s when needed.

### Safety

The plugin is the trust boundary: permissions, GriefPrevention claims, edit
budgets, deadlines, idempotency, verification, and undo are enforced after
model output. `mc-agent` publishes no host port. Prompts and inference stay
local.

### Template ranking

Natural-language prompts like *"a place for chickens to live"* resolve through
the companion template ranker against the curated catalog (101 `.schem`
files). See [docs/TEMPLATE_RANKING.md](docs/TEMPLATE_RANKING.md).

Obsolete RCON-orchestrator surfaces are listed in
[docs/DEPRECATED.md](docs/DEPRECATED.md).

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
- **`Connection throttled! Please wait before reconnecting.`** — Geyser
  presents every Bedrock player and playit collapses Java IPs through one
  gateway, so Paper's default 4 s join cooldown drops the second person.
  `config/patches/bukkit-overrides.json` disables this on every boot; if
  you see it, check that `data/bukkit.yml` has `connection-throttle: -1`
  after the next restart and that `PATCH_DEFINITIONS=/patches` is still
  set on the `mc` service.

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
├── companion/                  # Greenfield async runtime, routing, model, SQLite
├── protocol/                   # Language-neutral envelopes and tool contracts
├── skills/                     # Declarative, evaluated sidekick skills
├── evals/                      # Locked scorecard and release gates
├── agent/templates/            # Curated assets retained during migration
│   ├── catalog.json
│   └── schematics/*.schem      # 101 verified
├── plugins/neighborhood-agent/ # Native Paper gateway and tool executors
├── mc.sh, op.sh                # RCON / admin wrappers
├── scripts/                    # bootstrap, build-plugin, agent-smoke, eval, seed,
│                               # playit_setup, print_invite, etc.
├── tests/                      # 170+ unit / contract tests
├── docs/                       # ARCHITECTURE, TOOL_CONTRACT, HOSTING, CORPUS, ...
├── .cursor/                    # project rules (alwaysApply)
├── secrets/rcon_password       # gitignored
├── .env                        # gitignored
├── data/                       # world + plugins (gitignored)
└── backups/                    # mc-backup output (gitignored)
```
