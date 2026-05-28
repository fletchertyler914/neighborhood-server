# Contributing

## Prerequisites

- Docker Compose (Minecraft + mc-agent)
- Python 3.11+
- Ollama (for live eval on self-hosted runner)

## Development workflow

1. Change tool contracts in `agent/tool_registry.py` only (not duplicate lists elsewhere).
2. Implement behavior in `agent/tools.py`.
3. Add eval cases under `agent/eval/cases/`.
4. Run tests: `PYTHONPATH=. pytest -q`
5. Run spec eval locally: `./scripts/eval.sh spec`

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
```

## Model comparison

```bash
AGENT_COMPARE_MODELS=qwen2.5:7b-instruct,qwen3:8b ./scripts/compare-models.sh
```
