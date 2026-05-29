# Contributing

Welcome! This project is MIT-licensed. By contributing you agree that your
work is published under the same terms. Please be kind in issues and PRs.

## Prerequisites

- Docker Compose (Minecraft + mc-agent)
- Python 3.11+
- Ollama (for live eval and the in-game agent loop)

## Local setup

```bash
git clone <fork-url> neighborhood-server
cd neighborhood-server
make bootstrap         # detects deps, generates secrets/.env, picks Ollama path
make up                # boots Paper + agent + sidecars (+ ollama if profile chosen)
make plugin            # builds + installs the Paper /agent plugin JAR
make seed              # one-time: build all 101 .schem files in-world
make test              # 170+ unit / contract tests, no live server needed
```

## Development workflow

1. Change tool contracts in `agent/tool_registry.py` only (not duplicate lists elsewhere).
2. Implement behavior in the appropriate submodule under `agent/tools/`
   (`admin.py`, `builders.py`, `fawe.py`, `inspection.py`, `templates.py`,
   or `_monolith.py` for the still-unsplit shared helpers).
3. Bump `TOOLS_VERSION` (registry) and `TOOLS_VERSION_EXPECTED`
   (`agent/mcp_core.py`) — they must match.
4. Add eval cases under `agent/eval/cases/`.
5. Run tests: `make test` (or `PYTHONPATH=. pytest -q --ignore=tests/integration`).
6. Run spec eval locally: `make eval` — it auto-detects an online player
   and compares against `agent/eval/baseline.strict.json`.
7. Rebuild the orchestrator: `docker compose up -d --build mc-agent` (or
   `make up`).

For the full local loop (Docker spin-up, template seeding, live validation,
agent smoke, feedback capture, dataset export, and local trained-model usage),
see [docs/DEVELOPMENT_WORKFLOW.md](docs/DEVELOPMENT_WORKFLOW.md).

## Adding a tool

See [docs/TOOL_CONTRACT.md](docs/TOOL_CONTRACT.md).

## Eval gates

PRs must pass:

- All unit tests including `test_eval_fixture_gate` and `test_eval_coverage`
- Schema/registry/dispatch sync

Self-hosted CI additionally runs live spec eval against `baseline.strict.json`.

## Exporting training data

```bash
./scripts/export-dataset.sh datasets/reviews/raw/export.jsonl
PYTHONPATH=. python3 -m agent.training feedback \
  --sft-out datasets/sft/from-feedback.jsonl \
  --dpo-out datasets/preferences/from-feedback.jsonl
```

## Model comparison

```bash
AGENT_COMPARE_MODELS=qwen2.5:7b-instruct,qwen3:8b ./scripts/compare-models.sh
```

## Validation shortcuts

The Makefile auto-detects an online player via `scripts/_detect_player.sh`
so most contributors never have to set `AGENT_*_PLAYER` manually.

```bash
make test                                  # unit + contract (no live server)
make smoke                                 # 26 NL prompts → live LLM → orchestrator
make eval                                  # 19-case strict spec eval
make live-tools                            # RCON-driven tool integration
make full-validation                       # paste every template + summon every mob
./scripts/validate-all.sh                  # fast offline validation
RUN_LIVE=1 ./scripts/validate-all.sh       # also runs live-tools
RUN_FULL_WORLD=1 ./scripts/validate-all.sh # plus full-validation (slow)
make corpus-quick                          # 30-prompt NL corpus smoke (live world)
make corpus                                # full ~612-prompt corpus (~3h)
make triage                                # failure buckets from latest corpus run
make train                                 # export SFT/DPO + LoRA dry-run
```

## Coding style

- Python: standard library + `httpx`, `fastapi`, `pydantic`. Keep new
  dependencies behind a strong justification.
- Tests: prefer fast pure-Python tests next to the feature. Live tests
  go under `tests/integration/` and are gated by env vars so a fresh clone
  with no Minecraft running still gets `make test` green.
- Logging: use the `neighborhood.agent.*` named loggers. Don't print().
- Comments: explain *why*, not *what*. Skip narration like `# import json`.

## Submitting a pull request

1. Open an issue first for anything bigger than a small fix or new test.
2. Branch from `main`, keep commits logical (one concept per commit).
3. `make test` and (if applicable) `make smoke` / `make eval` should be
   green locally before you push.
4. Update `CHANGELOG.md` under `[Unreleased]` with a one-line description.
5. Open the PR with the prompt → tool-trace before/after if it changes
   agent behavior. Screenshots of in-game results are very welcome.
