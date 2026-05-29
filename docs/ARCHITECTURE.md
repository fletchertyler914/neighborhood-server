# Neighborhood Agent Architecture

## Overview

The in-game agent stack connects players, an LLM orchestrator, typed
Minecraft tools, and an evaluation harness.

```text
Player (/agent) ─► Paper plugin ─► mc-agent orchestrator ─► agent.tools ─► RCON ─► Paper server
Cursor MCP      ─► minecraft_build_mcp.py ─────────────────┘
Eval harness    ─► agent.eval ─────────────────────────────┘
```

## Compose services

| Service | Image | Container | Role |
| --- | --- | --- | --- |
| `mc` | `itzg/minecraft-server:java25` | `mc-lan` | Paper 26.1.2 + Geyser + Floodgate + FAWE |
| `mc-agent` | local build (`agent/Dockerfile`) | `mc-agent` | FastAPI orchestrator — no host port |
| `playit` | `ghcr.io/playit-cloud/playit-agent` | `playit-agent` | TCP/UDP relay (host network) |
| `backup` | `itzg/mc-backup` | `mc-backup` | RCON-coordinated 2h snapshots |
| `ollama` (profile `ollama`) | `ollama/ollama` | `mc-ollama` | Optional bundled LLM (no host install) |
| `ollama-pull` (profile `ollama`) | `ollama/ollama` | `mc-ollama-pull` | One-shot model pull on first boot |

Mac Apple Silicon: keep `--profile ollama` off and run host Ollama (Metal
GPU). Linux/Windows: turn the profile on via `make bootstrap` (writes
`COMPOSE_PROFILES=ollama` and `OLLAMA_BASE_URL=http://ollama:11434` to `.env`).

## Single source of truth: tool registry

All tool contracts live in [`agent/tool_registry.py`](../agent/tool_registry.py):

- `TOOL_DEFINITIONS` — name, description, JSON parameters, risk, category
- `build_openai_schemas()` → LLM tool schemas ([`agent/schema.py`](../agent/schema.py))
- `build_dispatch()` → runtime handlers in [`agent/tools/`](../agent/tools/) package
- `mcp_tool_names()` → MCP exposure ([`mcp/minecraft_build_mcp.py`](../mcp/minecraft_build_mcp.py))

Current `TOOLS_VERSION` is `2.9.0`. Bump it (in both `agent/tool_registry.py`
and `agent/mcp_core.py::TOOLS_VERSION_EXPECTED`) when changing tool
parameters or semantics. Eval baselines and export rows record this version.

## Orchestrator

- Package: [`agent/orchestrator/`](../agent/orchestrator/)
- Entrypoint: `python -m agent.orchestrator` (run as the `mc-agent` Compose
  service from `agent/Dockerfile`)
- Endpoints: `POST /v1/jobs`, `GET /health`, `GET /capabilities`,
  `GET /metrics` (Prometheus)
- Auth: `Authorization: Bearer ${AGENT_API_TOKEN}` — required, no fallback.
  Compose interpolates with `${AGENT_API_TOKEN:?...}` so boot fails fast if
  the variable is missing.

## Evaluation harness

| Tier | Command | Gates |
|------|---------|-------|
| Unit | `make test` (`pytest`) | Assertions, coverage matrix, schema sync, fixture replay |
| Tool integration (live) | `AGENT_LIVE_TOOL_PLAYER=<name> ./scripts/live-tool-tests.sh` or `make live-tools` | Direct `agent.tools` calls against Paper + RCON state probes |
| Spec (live) | `make eval` / `./scripts/eval.sh spec` | Dry-run tool trajectories vs baseline |
| Agent smoke (live) | `make smoke` | Real `/v1/jobs` with the local model on 26 NL prompts |
| Full world (live) | `make full-validation` / `python3 scripts/full_validation.py` | Paste every catalog template + summon every supported mob |
| World corpus (live) | `make corpus-quick` / `make corpus` | 612-prompt NL corpus with world probes |

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
2. `make corpus` or `./scripts/export-dataset.sh` → JSONL exports under `datasets/`
3. `/agent good|bad` ratings → `data/agent-feedback.jsonl` (linked by `job_id`)
4. `make training-data` → merged SFT + DPO JSONL
5. `make train` (dry-run) or `make train-full` (LoRA → GGUF → Ollama register)

See [docs/FINE_TUNING.md](FINE_TUNING.md) for the full pipeline.

## CI workflows

- `eval-spec.yml` — unit tests + fixture gate + coverage (every PR)
- `eval-spec-live.yml` — live spec + strict baseline (self-hosted)
- `eval-live-tools.yml` — deterministic direct tool execution checks (self-hosted)
- `eval-world.yml` — live world eval (self-hosted, scheduled)
