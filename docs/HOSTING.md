# Hosting a Neighborhood Party

Operations runbook for running a live crossplay session with friends.

For first-time setup of the stack, see
[PUBLIC_QUICKSTART.md](PUBLIC_QUICKSTART.md). For agent internals, see
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## Pre-party preflight (5 minutes)

```bash
make status            # mc-lan + mc-agent should both show (healthy)
make health            # GET /health from mc-agent
./mc.sh list           # confirms RCON works
./mc.sh backup         # snapshot the launch world before guests join
```

Visual check in-game:

- Connect from your own client at `localhost:25565` (Java) or
  `localhost:19132` (Bedrock).
- Spawn shows the new world (mountains/forest/whatever — not flat).
- Type `/agent say hello` to confirm `/agent` answers from the host LLM.

If anything is red, the most common fixes are:

```bash
docker compose restart mc-agent        # nudge the agent if /health fails
docker compose up -d --build mc-agent  # full rebuild if it drifted
make logs                              # tail mc-lan + mc-agent together
```

---

## Sharing the address with guests

The playit tunnel addresses live on your **playit.gg dashboard**, not in
local logs (the agent only sees the relay endpoints). Open
[playit.gg/account/tunnels](https://playit.gg/account/tunnels) and copy:

- **Java edition** (TCP / 25565) → e.g. `xyz-abc.gl.joinmc.link`
- **Bedrock edition** (UDP / 19132) → e.g. `xyz-abc.gl.joinmc.link:NNNNN`

Paste both into the party invite.

### Whitelist mode (default, recommended)

`ENFORCE_WHITELIST` is **on** by default in the public repo. Add every guest
before sharing the address:

```bash
./mc.sh cmd "whitelist add <java_name>"
./mc.sh cmd "whitelist add .<bedrock_gamertag>"   # leading dot for Bedrock
```

### Open friends-server mode

For "anyone with the address can join", set `MC_ENFORCE_WHITELIST=false` in
`.env` and `docker compose restart mc`. To lock it back down on the fly
without restarting:

```bash
./mc.sh cmd "whitelist add <name>"
./mc.sh cmd "whitelist on"
```

---

## Common party operations

Everything below uses the `mc.sh` / `op.sh` wrappers so you stay out of raw
`docker exec`. Full list lives in
[02-minecraft-tools](../.cursor/rules/02-minecraft-tools.mdc).

### Promote a friend to OP

```bash
./op.sh someFriend                     # Java edition
./op.sh .someBedrockFriend             # Bedrock — leading dot is required
```

OPs are persisted across restarts via `EXISTING_OPS_FILE: MERGE`.

### Quick admin

```bash
./mc.sh say "Welcome <name>!"
./mc.sh gamemode creative <name>
./mc.sh cmd "time set day"
./mc.sh cmd "weather clear 30000"
./mc.sh cmd "tp <name> 0 100 0"
```

### Use `/agent` in chat (OP-only by default)

Examples that the corpus regression-tests pass on every release:

```text
/agent build me a cottage in front of me
/agent give me a few pigs
/agent dig a 30-block staircase down to bedrock
/agent build a hollow stone-brick sphere radius 8 above me
/agent confirm <token> clear a 20x20 area around me     # destructive ops
```

The orchestrator routes through local Ollama (`qwen2.5:7b-instruct` by
default) first; cloud (`OPENAI_API_KEY`) is the third-tier fallback.

### Forgot the agent token

`AGENT_API_TOKEN` is in `.env`. Players don't need it — it only matters for
the Paper plugin → orchestrator handshake. If you ever wipe `.env`, regenerate
with `make bootstrap` and `docker compose up -d --build mc-agent` so the new
token reaches the container.

---

## During-party recovery

| Symptom | Quick fix |
| --- | --- |
| Player stuck under the world | `./mc.sh cmd "tp <name> 0 100 0"` then `/spawnpoint @s` |
| `/agent` says "Agent offline" | `docker compose ps mc-agent` ; `docker compose restart mc-agent` |
| `/agent` says "Agent misconfigured" | `AGENT_API_TOKEN` missing — set in `.env` and rebuild `mc-agent` |
| Bundled Ollama timing out | `docker compose logs mc-ollama` ; first prompt loads model into RAM |
| Server lag spike | `./mc.sh cmd "tps"` ; if persistent, `./mc.sh cmd "spark profile"` |
| Someone griefs | `./mc.sh cmd "ban <name>"` ; restore from latest backup if needed |
| Bedrock friend can't connect | Confirm UDP port `19132` tunnel is online on the playit dashboard |

A backup runs automatically every 2h via `mc-backup` (RCON-coordinated
`save-off` / `save-on`, 14-day retention). To roll back:

```bash
ls -lt backups | head             # find a snapshot before the incident
docker compose stop mc
mv data/world data/world.bad
tar -xzf backups/world-YYYY-MM-DD-HH-MM-SS.tgz -C data/
docker compose start mc
```

---

## Post-party

Save anything cool from the session before the next dev cycle:

```bash
./mc.sh backup                                       # final snapshot
cp backups/world-$(date +%Y-%m-%d)*.tgz \
   backups/keep-party-$(date +%Y%m%d).tgz           # rename outside the prune window
```

If you want to extract a particular build as a reusable template, jump into
the world as an OP, select with `//pos1`/`//pos2`, then:

```text
//copy
//schem save <name>
```

The schematic lands in `data/plugins/FastAsyncWorldEdit/schematics/` and
can be copied into `agent/templates/schematics/` (and added to
`agent/templates/catalog.json`) so `/agent` and the Cursor MCP can paste it
later. See [docs/TEMPLATES.md](TEMPLATES.md) for the full publish workflow.

---

## Tunables worth knowing

The `mc` service in `docker-compose.yml` ships with sensible defaults for a
friends-scale server. Common knobs (override in `.env` via the standard
itzg env vars or by editing compose):

| Setting | Default | Purpose |
| --- | --- | --- |
| `MAX_MEMORY` | `8G` | JVM heap ceiling (ZGC + generational) |
| `mem_limit` (container) | `10g` | Hard container cap |
| `VIEW_DISTANCE` | `12` | Chunks visible to each player |
| `SIMULATION_DISTANCE` | `6` | Chunks ticking around each player |
| `MOTD` (`MC_MOTD`) | "Neighborhood Server" | What appears in the server list |
| `MC_ENFORCE_WHITELIST` | `true` | Flip to `false` for open friends mode |

Backups under `backups/` exclude `_reset_archives/`, `corpus-runs/`, and
`eval-runs/` so daily snapshots stay small (~3 MB) instead of bloating with
eval data.
