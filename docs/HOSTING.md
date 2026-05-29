# Hosting a Neighborhood Party

Operations runbook for running a live crossplay session with friends.

For first-time setup of the stack, see
[PUBLIC_QUICKSTART.md](PUBLIC_QUICKSTART.md). For agent internals, see
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## Pre-party preflight (5 minutes)

```bash
make status            # mc-lan + mc-agent should both show (healthy)
./mc.sh list           # confirms RCON works
./mc.sh backup         # snapshot the launch world before guests join
```

Visual check in-game:

- Connect from your own client at `localhost:25565` (Java) or
  `localhost:19132` (Bedrock).
- Spawn shows the new world (mountains/forest/whatever - not flat).
- Type `/agent say hello` to confirm `/agent` answers from the host LLM.

If anything is red, the most common fix is:

```bash
docker compose restart mc-agent       # nudge the agent if /health fails
docker compose up -d --build mc-agent # full rebuild if it drifted
```

---

## Sharing the address with guests

The playit tunnel addresses live on your **playit.gg dashboard**, not in
local logs (the agent only sees the relay endpoints). Open
[playit.gg/account/tunnels](https://playit.gg/account/tunnels) and copy:

- **Java edition** (TCP / 25565) -> something like `xyz-abc.gl.joinmc.link`
- **Bedrock edition** (UDP / 19132) -> something like `xyz-abc.gl.joinmc.link:NNNNN`

Paste both into the party invite. Reminder: whitelist is **OFF** by
default for the friends server, so anyone with the address can join.

To lock it down on the fly without restarting:

```bash
./mc.sh cmd "whitelist add <name>"
./mc.sh cmd "whitelist on"
```

---

## Common party operations

Everything below uses the `mc.sh` and `op.sh` wrappers so you stay out of
raw `docker exec`. Full list lives in [02-minecraft-tools](../.cursor/rules/02-minecraft-tools.mdc).

### Promote a friend to OP

```bash
./op.sh someFriend                     # Java edition
./op.sh .someBedrockFriend             # Bedrock - leading dot is required
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
/agent confirm <token> clear a 20x20 area around me   # destructive ops
```

The orchestrator is local Ollama -> qwen2.5:7b-instruct by default. If
you have `OPENAI_API_KEY` in `.env`, cloud is the third-tier fallback.

### Forgot the agent token

`AGENT_API_TOKEN` is in `.env`. Players don't need it - it only matters
for direct HTTP calls to `mc-agent`.

---

## During-party recovery

| Symptom | Quick fix |
| --- | --- |
| Player stuck under the world | `./mc.sh cmd "tp <name> 0 100 0"` then `/spawnpoint @s` |
| `/agent` says "Agent offline" | `docker compose ps mc-agent` ; `docker compose restart mc-agent` |
| Server lag spike | `./mc.sh cmd "tps"` ; if persistent, `./mc.sh cmd "spark profile"` |
| Someone griefs | `./mc.sh cmd "ban <name>"` ; restore from latest backup if needed |
| Bedrock friend can't connect | confirm UDP port `19132` tunnel is showing on playit dashboard |

A backup runs automatically every 2h via `mc-backup` (RCON-coordinated
`save-off` / `save-on`, 14-day retention). To roll back:

```bash
ls -lt backups | head             # find a snapshot before the incident
docker compose stop mc
mv data/world data/world.bad
tar -xzf backups/world-YYYYMMDD-HHMMSS.tar.gz -C data/
docker compose start mc
```

---

## Post-party

Save anything cool from the session before the next dev cycle:

```bash
./mc.sh backup                                       # final snapshot
cp backups/world-$(date +%Y%m%d)*.tar.gz \
   backups/keep-party-$(date +%Y%m%d).tar.gz        # rename outside the prune window
```

If you want to extract a particular build as a reusable template, jump
into the world as an OP, select with `//pos1`/`//pos2`, then:

```text
//copy
//schem save <name>
```

The schematic lands in `data/plugins/FastAsyncWorldEdit/schematics/` and
can be copied into `agent/templates/schematics/neighborhood/` so
`/agent` can paste it later.

---

## What changed for the launch

For posterity (commit log has details):

- Memory: `MAX_MEMORY 8G`, container `mem_limit 10g`
- World: vanilla `minecraft:normal` terrain (not flat). Validation flat
  world archived under `data/_reset_archives/<timestamp>-pre-launch/`.
- View distance: 12, simulation distance: 6
- MOTD: customizable via `MC_MOTD` in `.env`
- Backups: `_reset_archives/`, `corpus-runs/`, `eval-runs/` excluded so
  daily snapshots stay ~3 MB instead of ~100 MB
