# Deprecated surfaces (soft-retired)

The greenfield `/agent` sidekick is the companion WebSocket runtime
(`companion/` + Paper plugin native execution). The following are kept in-tree
for reference and gradual deletion, but are **not** the operator path.

## Do not use for new work

| Surface | Replacement |
| --- | --- |
| `agent/orchestrator` + HTTP `/v1/jobs` | `companion/` + `ws://mc-agent:8787/v1/gateway` |
| RCON tool dispatch for `/agent` (`AGENT_DISPATCH_TRANSPORT=rcon`) | Plugin-native execution |
| Cursor `minecraft-builder` MCP | In-game `/agent` only |
| `make agent-gate` / `make live-tools` / `make smoke` / `make eval` | `make companion-gate` / `make companion-live*` |
| `make corpus*` / training corpus runners | Companion eval fixtures under `evals/` |
| `agent/skills/` | `skills/` |
| Cloud LLM fallback (`OPENAI_API_KEY` orchestrator path) | Local Ollama only |

Makefile help labels the old validation targets as **(deprecated)**.

## Still useful (host ops, not sidekick)

- `./mc.sh` / RCON for whitelist, op, backups, console
- Template catalog under `agent/templates/` (schematics still mounted for paste)
