# Neighborhood Agent Architecture

## Overview

The in-game agent stack connects players, an LLM orchestrator, typed Minecraft tools, and an evaluation harness.

```text
Player (/agent) → Paper plugin → mc-agent orchestrator → agent.tools (RCON) → Paper server
Cursor MCP      → minecraft_build_mcp.py ────────────────┘
Eval harness    → agent.eval ────────────────────────────┘
```

## Single source of truth: tool registry

All tool contracts live in [`agent/tool_registry.py`](../agent/tool_registry.py):

- `TOOL_DEFINITIONS` — name, description, JSON parameters, risk, category
- `build_openai_schemas()` → LLM tool schemas ([`agent/schema.py`](../agent/schema.py))
- `build_dispatch()` → runtime handlers ([`agent/tools.py`](../agent/tools.py))
- `mcp_tool_names()` → MCP exposure ([`mcp/minecraft_build_mcp.py`](../mcp/minecraft_build_mcp.py))

Bump `TOOLS_VERSION` when changing tool parameters or semantics. Eval baselines and export rows record this version.

## Evaluation harness

| Tier | Command | Gates |
|------|---------|-------|
| Unit | `pytest` | Assertions, coverage matrix, schema sync, fixture replay |
| Tool integration (live) | `AGENT_LIVE_TOOL_PLAYER=firecrab93 ./scripts/live-tool-tests.sh` | Direct `agent.tools` calls against Paper + RCON state probes |
| Spec (live) | `./scripts/eval.sh spec` | Dry-run tool trajectories vs baseline |
| World (live) | `AGENT_EVAL_ALLOW_WORLD_MUTATION=1 ./scripts/eval.sh world` | RCON world probes |

Tool integration tests are the contract for whether the typed tools execute
correctly on a real server. Agent evals should only answer whether a model
chooses the right tool and arguments from natural language.

Supporting modules:

- `agent/eval/coverage.yaml` — required case IDs by intent family
- `agent/eval/quarantine.yaml` — temporarily skipped cases
- `agent/eval/strategy.py` — prompt strategy presets for experiments
- `agent/eval/compare.py` — multi-model comparison
- `agent/eval/export.py` — JSONL export for training/review

## Training loop (foundation)

1. Run eval or production → audit log + eval reports
2. `./scripts/export-dataset.sh` → `datasets/reviews/raw/export.jsonl`
3. Human review labels → `agent/training/pairs.py` → preference pairs JSONL
4. Future: fine-tune / DPO on exported traces

## CI workflows

- `eval-spec.yml` — unit tests + fixture gate + coverage (every PR)
- `eval-spec-live.yml` — live spec + strict baseline (self-hosted)
- `eval-live-tools.yml` — deterministic direct tool execution checks (self-hosted)
- `eval-world.yml` — live world eval (self-hosted, scheduled)
