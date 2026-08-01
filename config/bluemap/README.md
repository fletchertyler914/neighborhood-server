# `config/bluemap/` — BlueMap baseline config

BlueMap is installed via `MODRINTH_PROJECTS: bluemap` in `docker-compose.yml`
and serves a 3D web map of all worlds at `http://127.0.0.1:8100` after the
next `docker compose restart mc`.

The two files in this directory are bind-mounted on top of BlueMap's own
config dir at boot:

| File | Why we override |
| --- | --- |
| `core.conf` | Sets `accept-download: true` (BlueMap refuses to start without it because it fetches textures on first run) and caps `render-thread-count: 2` so tile rendering doesn't starve the game thread. |
| `webserver.conf` | Pins `ip: 0.0.0.0` + `port: 8100` so Docker can forward predictably to the host. |

BlueMap fills in defaults for everything else (per-world map configs land in
`data/plugins/BlueMap/maps/world.conf` etc. and you can edit those freely;
they're not bind-mounted).

## Changing access scope

The host-side lockdown is in `docker-compose.yml` under `mc.ports`:

```yaml
- '127.0.0.1:8100:8100/tcp'   # me only — default
- '0.0.0.0:8100:8100/tcp'     # me + anyone on my home LAN
```

To share the map publicly alongside the game, add a third **TCP** tunnel in
the playit dashboard pointing at local port 8100 and use that URL.

## Updating BlueMap

`MODRINTH_PROJECTS` re-pulls latest on every container restart. Your config
overrides survive because they're bind-mounted from outside the data
volume.
