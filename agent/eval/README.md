## Neighborhood Agent Eval Harness

This harness runs deterministic, YAML-defined evaluation cases against the local orchestrator.

### Modes

- **spec**: `dry_run=true` jobs; validates tool-call trajectories and safety behaviors.
- **world**: live world mutations inside a sandbox box (implemented separately).

### Environment

The runner expects the orchestrator to be reachable and eval mode enabled:

- `AGENT_EVAL_MODE=1`
- `AGENT_EVAL_MODEL=<model>` (optional)
- `AGENT_EVAL_DISABLE_RETRIEVAL=1` (optional for strict suites)
- `AGENT_EVAL_DISABLE_DYNAMIC_CONTEXT=1` (optional for strict suites)

### Run

```bash
./scripts/eval.sh spec
```

The script runs against a host-published orchestrator if available. If not, it
falls back to `docker exec mc-agent` and evaluates the private Compose service
from inside the container.

### Baselines

Strict baselines are merge-gating:

```bash
EVAL_COMPARE_BASELINE=agent/eval/baseline.strict.json ./scripts/eval.sh spec
```

To intentionally refresh a baseline after reviewing the diff:

```bash
EVAL_SAVE_BASELINE=agent/eval/baseline.strict.json ./scripts/eval.sh spec
```

### World Eval Safety

World eval mutates the server. It fails closed unless explicitly enabled:

```bash
AGENT_EVAL_ALLOW_WORLD_MUTATION=1 ./scripts/eval.sh world
```

World cases should only target a known eval player and sandbox. Do not run them
on a busy live server.

### Live tool integration tests

Use deterministic live tests to verify the tool implementations themselves,
without an LLM in the loop:

```bash
AGENT_LIVE_TOOL_PLAYER=JavaTester ./scripts/live-tool-tests.sh
```

These tests call `agent.tools` directly and probe server state through RCON.
They mutate and clean a fixed sandbox region (`9100,80,9100` through
`9130,100,9130` by default). If no player is configured, player-relative tests
are skipped but absolute block/tool tests still run.

### Quarantine

`quarantine.yaml` is intentionally explicit. Entries must include an owner,
reason, and expiry date. Quarantine is for temporary triage only, not hiding
regressions.

### Coverage gate

`coverage.yaml` lists required case IDs by intent family. The runner enforces
this when `AGENT_EVAL_ENFORCE_COVERAGE=1` (default). CI runs
`tests/test_eval_coverage.py`.

### Job envelopes

Each run writes `report.json` plus `envelopes.jsonl` — canonical rows keyed by
`job_id` that merge eval traces with audit log entries.

### Dataset export

```bash
./scripts/export-dataset.sh datasets/reviews/raw/export.jsonl
```

### Model / strategy comparison

```bash
AGENT_COMPARE_MODELS=qwen2.5:7b-instruct,qwen3:8b ./scripts/compare-models.sh
```

Strategies: `baseline`, `full_context`, `retrieval_only` (see `agent/eval/strategy.py`).

### Training prep

Label review rows in JSONL, then build preference pairs:

```bash
python -m agent.training pairs reviews.jsonl datasets/preferences/pairs.jsonl
```

See [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) and [docs/TOOL_CONTRACT.md](../../docs/TOOL_CONTRACT.md).
For the end-to-end developer loop (spin-up, validation tiers, feedback export,
fine-tuning prep, and local trained-model usage), see
[docs/DEVELOPMENT_WORKFLOW.md](../../docs/DEVELOPMENT_WORKFLOW.md).

