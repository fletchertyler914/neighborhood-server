# `config/patches/` — itzg PATCH_DEFINITIONS

Each `*.json` in this directory is one
[itzg/minecraft-server patch definition](https://docker-minecraft-server.readthedocs.io/en/latest/misc/file-patching/).
The `mc` service mounts this directory read-only at `/patches` and sets
`PATCH_DEFINITIONS=/patches`, so every patch is applied on every container
boot (before the JVM starts).

This is how we keep server config "correct" without checking the full
`data/bukkit.yml` / `data/spigot.yml` files into git.

## `bukkit-overrides.json` — disable connection-throttle

Paper's `settings.connection-throttle` defaults to 4000 ms. When running
with Geyser + Floodgate + playit (this stack's default):

- Geyser presents every Bedrock player to Paper as coming from the local
  Geyser bridge (`127.0.0.1` or `0.0.0.0`).
- playit's tunnel collapses public Java IPs into a small set of gateway
  hops.

So any second player joining within 4 seconds of the previous one gets
disconnected with `Connection throttled! Please wait before reconnecting.`,
even though they're not abusing anything. GeyserMC's own setup guide
recommends setting this to `-1`, which is what we do here.

Symptom in logs:

```text
[Geyser-Spigot] <name> has disconnected from the Java server because of
Connection throttled! Please wait before reconnecting.
```
