# Hosting a Neighborhood Family Party

Operations runbook for a supervised home / family weekend with the local
`/agent` sidekick. First-time setup: [PUBLIC_QUICKSTART.md](PUBLIC_QUICKSTART.md).
Internals: [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Parent one-pager (read this once)

### Who can use `/agent`?

- **Not related to single-player “cheats.”** Paper uses Bukkit permissions.
- Family defaults: every player can use `/agent` (time, weather, give, friendly
  mobs, templates, finish wall, undo) **without being op**.
- **Whitelist** controls who joins the server — it is not an `/agent` switch.
- **GriefPrevention** is the real build guardrail. Kids claim land; the
  sidekick will not paste/build in someone else’s claim unless trusted.
- For an open/public server where strangers join, tighten permissions to `op`
  (or LuckPerms groups) so not every joiner gets the sidekick.

### What the sidekick will / won’t do

| Will | Won’t |
| --- | --- |
| Day/night, clear rain | Dig / clear huge areas |
| Give safe items (ask “how many?”) | Hostile mobs, dangerous items |
| Friendly animals | Bypass GriefPrevention claims |
| Paste curated builds (coop, cottage, …) | Arbitrary WorldEdit / raw commands |
| Finish a wall between two posts | Cloud AI — inference stays local |
| Undo the last sidekick action | |

### Bedrock names

Bedrock players appear with a leading `.` (Floodgate), e.g. `.Alex`. Include
the dot in whitelist / op / trust commands.

### Sibling servers (claim basics)

1. Each kid: hold a **golden shovel**, right-click two opposite corners to claim.
2. Share a build plot: `/trust <friend>` (or `/containertrust` for chests only).
3. Auto-claim may grant a starter claim on first join — still teach shovel claims
   for bigger bases.
4. If the sidekick says “someone’s claim”, the builder needs `/trust`.

### Non-Mac hosts

Default model story is Apple Silicon `gemma4:12b-mlx`. On Linux/Windows use a
local instruct model (e.g. `qwen2.5:7b-instruct`). Common asks stay fast;
expect slower Tier-B (model) latency — do not promise Mac parity.

### BlueMap

Live map is **localhost-only** by default (`http://127.0.0.1:8100`). Do not
expose it on the public internet without an auth front door. See
`config/bluemap/README.md`.

---

## Release checklist (before guests)

```bash
make status
make health
make companion-gate              # offline accuracy + latency
make companion-live              # needs an online player
make companion-live-dialogue
./mc.sh backup
```

### Honest latency SLOs (warm Mac Mini-class host)

| Path | Expect |
| --- | --- |
| Common (time/weather/give/mobs) | ≤ 500 ms |
| Builds (wall / template paste) | ~0.2–2 s |
| Model compile (ambiguous asks) | ~3–6 s (gate: median ≤4500 ms, max ≤8000 ms) |

---

## Pre-party preflight (5 minutes)

```bash
make status            # mc-lan + mc-agent should both show (healthy)
make health            # GET /health from mc-agent
./mc.sh list           # confirms RCON works for ops scripts
./mc.sh backup         # snapshot before guests join
```

In-game:

- Connect at `localhost:25565` (Java) or `localhost:19132` (Bedrock).
- Type `/agent` (empty) for the capability card, then `/agent make it daytime`.

If anything is red:

```bash
docker compose restart mc-agent
docker compose up -d --build mc-agent
make logs
```

---

## Sharing the address with guests

Playit tunnel addresses live on your **playit.gg dashboard**. Copy:

- **Java** (TCP / 25565)
- **Bedrock** (UDP / 19132)

### Whitelist mode (default, recommended)

```bash
./mc.sh cmd "whitelist add <java_name>"
./mc.sh cmd "whitelist add .<bedrock_gamertag>"
```

### Open friends-server mode

Set `MC_ENFORCE_WHITELIST=false` in `.env` and `docker compose restart mc`.
Do this intentionally — strangers with the address can join. Consider
tightening `/agent` permissions to `op` if the party is not family-only.

---

## Common party operations

### Promote a friend to OP (optional)

```bash
./op.sh someFriend
./op.sh .someBedrockFriend
```

Kids do **not** need op for the sidekick on family defaults.

### Quick admin

```bash
./mc.sh say "Welcome!"
./mc.sh gamemode creative <name>
./mc.sh cmd "time set day"
./mc.sh backup
```

### Protect builds (GriefPrevention)

```text
/trust <player>
/containertrust <player>
/untrust <player>
/trustlist
```

### Use `/agent` in chat

```text
/agent make it daytime
/agent give me three dirt
/agent spawn three chickens
/agent build me a small chicken coop
/agent finish this wall in front of me 8 blocks high
/agent undo that
/agent can i have torch
12
```

### Forgot the agent token

`AGENT_API_TOKEN` is in `.env` (plugin ↔ companion handshake only). Regenerate
with `make bootstrap` and rebuild `mc-agent` if wiped.

---

## During-party recovery

| Symptom | Quick fix |
| --- | --- |
| Player stuck | `./mc.sh cmd "tp <name> 0 100 0"` |
| Sidekick offline | `docker compose restart mc-agent` |
| Sidekick misconfigured | Set `AGENT_API_TOKEN` in `.env`, rebuild `mc-agent` |
| Model slow / timeout | Warm Ollama (`ollama run gemma4:12b-mlx`); simplify the ask |
| Someone griefs | GP claims first; restore from backup for severe damage |
| Bedrock can't connect | Check UDP `19132` tunnel on playit dashboard |
| `Connection throttled!` | `config/patches/bukkit-overrides.json` should keep throttle at `-1` |
| Want a map? | BlueMap at <http://127.0.0.1:8100> (localhost only) |

### Restore a backup

```bash
ls -lt backups | head
docker compose stop mc
mv data/world data/world.bad
tar -xzf backups/world-YYYY-MM-DD-HH-MM-SS.tgz -C data/
docker compose start mc
```

---

## Post-party

```bash
./mc.sh backup
cp backups/world-$(date +%Y-%m-%d)*.tgz \
   backups/keep-party-$(date +%Y%m%d).tgz
```

To save a cool build as a reusable template, see [TEMPLATES.md](TEMPLATES.md).

---

## Tunables

| Setting | Default | Purpose |
| --- | --- | --- |
| `MAX_MEMORY` | `8G` | JVM heap |
| `VIEW_DISTANCE` | `12` | Visible chunks |
| `MC_ENFORCE_WHITELIST` | `true` | Flip to `false` for open friends mode |
| `LOCAL_LLM_MODEL` / `OLLAMA_MODEL` | `gemma4:12b-mlx` | Sidekick model |

Retired RCON-orchestrator surfaces: [DEPRECATED.md](DEPRECATED.md).
