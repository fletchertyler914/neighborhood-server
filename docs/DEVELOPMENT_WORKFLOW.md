# Development Workflow

This is the kitchen-sink runbook for the experimental agent stack: spin it up,
iterate on tools/templates/prompts, validate the real server, capture feedback,
build training data, and point the agent at a locally trained model.

## 1. First spin-up

```bash
make bootstrap                  # secrets, .env with AGENT_API_TOKEN, Ollama path choice
# (optional) edit .env: PLAYIT_SECRET_KEY=..., OPENAI_API_KEY=...

# Host Ollama path (Mac Metal GPU): pull the models locally.
ollama pull qwen2.5:7b-instruct
ollama pull qwen3:8b
# Bundled Ollama path: nothing extra — bootstrap set COMPOSE_PROFILES=ollama
# and `make up` will pull the model on first boot.

make up                         # docker compose up -d (+ ollama if profile active)
make plugin                     # builds the Paper plugin JAR + installs into data/plugins
make status                     # docker compose ps for the stack
```

Health checks:

```bash
make health                     # GET /health from mc-agent
./mc.sh status                  # all services
./mc.sh list                    # RCON sanity check
make logs                       # tail mc-lan + mc-agent together
docker compose logs -f mc-agent # just the orchestrator
```

The Paper plugin config (auto-installed by `make plugin`) should remain:

```yaml
orchestrator-url: http://mc-agent:8787
api-token: env:AGENT_API_TOKEN
```

Do not publish RCON or `mc-agent` ports. Cursor MCP and `/agent` both use the
same `agent/tools/` package (registry in `agent/tool_registry.py`) through the
private Docker network / container exec.

## 2. Daily dev loop

Common fast loop:

```bash
python3 -m pytest tests/ -q
PYTHONPATH=. python3 -m agent.eval.template_ranking_eval
docker compose up -d --build mc-agent
```

One-command non-mutating validation:

```bash
./scripts/validate-all.sh
```

With live server checks:

```bash
AGENT_LIVE_TOOL_PLAYER=JavaTester RUN_LIVE=1 ./scripts/validate-all.sh
```

With full world/corpus validation (mutates the flat validation area):

```bash
AGENT_LIVE_TOOL_PLAYER=JavaTester RUN_LIVE=1 RUN_FULL_WORLD=1 ./scripts/validate-all.sh
```

Representative real `/agent` prompt smoke through `mc-agent`:

```bash
AGENT_SMOKE_PLAYER=JavaTester ./scripts/agent-smoke.sh
```

This sends 26 natural-language prompts through `/v1/jobs` using the local model
and checks that the selected tool family matches expectation.

## 3. What to edit

| Goal | Edit |
| --- | --- |
| Add/change tool contract | `agent/tool_registry.py` |
| Implement tool behavior | `agent/tools/` (admin, builders, fawe, inspection, templates) |
| Add template metadata | `agent/templates/catalog.json` or ingestion helpers |
| Re-seed schematics | `agent/templates/seed.py` via `scripts/seed-templates.sh` |
| Improve NL template routing | `agent/templates/ranking.py`, `embedding_backend.py` |
| Improve agent prompting | `agent/prompts/system.md`, `agent/knowledge/*.md` |
| Add eval cases | `agent/eval/cases/*.yaml`, `agent/eval/coverage.yaml` |
| Expand feedback/training export | `agent/feedback.py`, `agent/training/` |

Important invariants:

- Tool definitions live once in `agent/tool_registry.py`; schemas, dispatch, and
  MCP exposure are derived from it.
- `paste_template_at_player` accepts natural language; the hybrid ranker resolves
  ids. Do not train or prompt the model to memorize snake_case catalog ids.
- Bump `TOOLS_VERSION` whenever parameters or semantics change, then update the
  corresponding test assertion in `tests/test_executor.py`.
- Rebuild `mc-agent` after Python/tool changes.

## 4. Template iteration

Create or edit templates in one of three ways:

```bash
# 1. Add metadata / generated fallback entries.
python3 -m agent.templates.ingest --apply-corpus-sprint

# 2. Re-seed one or more schematics from catalog fallback builders.
AGENT_SEED_PLAYER=JavaTester ./scripts/seed-templates.sh --all --only cottage_medium

# 3. Save a hand-built FAWE selection from in game.
# In Cursor/MCP or /agent tool call:
create_template_from_selection(player="JavaTester", template_id="my_new_template")
```

After changing builders that affect schematics:

```bash
AGENT_SEED_PLAYER=JavaTester ./scripts/seed-templates.sh --all --only <template_id>
PYTHONPATH=. python3 scripts/full_validation.py
```

`seed.py` deletes existing `.schem` files before save because FAWE's
`//schem save` is silently no-overwrite, and waits between FAWE commands because
`agentexec` schedules them one server tick at a time.

## 5. Validation tiers

| Tier | Command | Mutates world? | Purpose |
| --- | --- | --- | --- |
| Unit/contract | `python3 -m pytest tests/ -q` | No | Registry/schema/tool contracts, ranker, training, catalog |
| Ranking eval | `PYTHONPATH=. python3 -m agent.eval.template_ranking_eval` | No | Natural-language template resolution |
| Spec eval | `./scripts/eval.sh spec` | Dry-run | Model/tool trajectory vs baselines |
| Live tools | `AGENT_LIVE_TOOL_PLAYER=JavaTester ./scripts/live-tool-tests.sh` | Yes, sandbox | Direct `agent.tools` against Paper + RCON probes |
| Agent smoke | `AGENT_SMOKE_PLAYER=JavaTester ./scripts/agent-smoke.sh` | Yes | Real `/v1/jobs` prompt routing with local model |
| Full world | `PYTHONPATH=. python3 scripts/full_validation.py` | Yes, validation grid | Paste every catalog template + summon every supported mob |

Current known-good snapshot (`TOOLS_VERSION=2.9.0`):

- `pytest tests/`: 170+ passed.
- Live tools: 20/20 passed.
- Full world: 101/101 templates pasted via schematics, 0 fallbacks, 59/59 mobs.
- Agent smoke: 26/26 representative prompts routed to expected tool/template.

## 6. Feedback capture

After a successful tool-running job, the player can rate it:

```text
/agent good
/agent bad the bridge was too high
```

The orchestrator intercepts feedback before the LLM sees it and writes:

- `data/agent-audit.log` — all jobs/tool calls/routing context.
- `data/agent-feedback.jsonl` — ratings linked to the previous job.
- `data/template-ranking-audit.jsonl` — ranker candidates + confidence.

Quick report:

```bash
PYTHONPATH=. python3 -m agent.training feedback --report
```

## 7. Dataset buildup

The end-to-end NL → tool → world corpus + DPO loop lives in
`docs/CORPUS.md` and `docs/FINE_TUNING.md`. Quick entry points:

```bash
make corpus           # ~612 prompts, live world (~3h)
make corpus-quick     # 30-prompt smoke
make triage           # cluster failures from latest run
make feedback-report  # count /agent good|bad rows captured so far
make training-data    # corpus + feedback → datasets/sft/train.jsonl
                      # + datasets/preferences/train.jsonl
make train            # dry-run LoRA wiring against merged data
make train-full       # real LoRA → GGUF → ollama create
make compare-models   # stock qwen2.5 vs trained qwen2.5 (with latency)
```

Lower-level dataset helpers (still supported):

```bash
./scripts/export-dataset.sh datasets/reviews/raw/export.jsonl
PYTHONPATH=. python3 -m agent.training pairs \
  datasets/reviews/raw/export.jsonl \
  datasets/preferences/pairs.jsonl
PYTHONPATH=. python3 -m agent.training feedback \
  --sft-out datasets/sft/from-feedback.jsonl \
  --dpo-out datasets/preferences/from-feedback.jsonl
```

This repo prepares datasets; it does not currently run GPU training itself.
Fine-tune with your preferred trainer (Axolotl, Unsloth, LLaMA Factory, MLX,
OpenAI-compatible hosted fine-tuning, etc.), then export a local model artifact
you can serve through Ollama or any OpenAI-compatible local server.

## 8. Using a trained model locally

### Ollama model name

If your trained model is available to Ollama:

```bash
ollama list
ollama run neighborhood-agent-v1
```

Then set:

```env
OLLAMA_MODEL=neighborhood-agent-v1
OLLAMA_FALLBACK_MODEL=qwen2.5:7b-instruct
AGENT_LOCAL_MODEL_TIMEOUT_SEC=30
```

Restart:

```bash
docker compose up -d --build mc-agent
AGENT_SMOKE_PLAYER=JavaTester ./scripts/agent-smoke.sh
```

### GGUF via Ollama Modelfile

For a local GGUF:

```bash
cat > Modelfile.neighborhood <<'EOF'
FROM ./models/neighborhood-agent-v1.gguf
PARAMETER num_ctx 4096
PARAMETER temperature 0.1
SYSTEM """
You are the Neighborhood Minecraft agent. Use tools for all world actions.
"""
EOF

ollama create neighborhood-agent-v1 -f Modelfile.neighborhood
```

Then use the same `.env` values above.

### OpenAI-compatible local server

If the trained model is served by vLLM/llama.cpp/MLX-LM with an OpenAI-compatible
API, either point Ollama-compatible env vars at a shim, or use cloud fallback
envs against the local endpoint:

```env
OPENAI_API_KEY=local-dev-token
CLOUD_BASE_URL=http://127.0.0.1:8000/v1
CLOUD_MODEL=neighborhood-agent-v1
```

Keep `OLLAMA_MODEL=qwen2.5:7b-instruct` as a fallback until the trained model
passes the agent smoke, live tools, and full world validation gates.

## 9. Release readiness checklist

Before treating a branch as a stable foundation:

```bash
./scripts/validate-all.sh
AGENT_LIVE_TOOL_PLAYER=JavaTester RUN_LIVE=1 ./scripts/validate-all.sh
AGENT_SMOKE_PLAYER=JavaTester ./scripts/agent-smoke.sh
PYTHONPATH=. python3 scripts/full_validation.py
git status -s
```

Then update:

- `README.md` if the public workflow changed.
- `.cursor/rules/*.mdc` if agent behavior or safety rules changed.
- `docs/TEMPLATE_RANKING.md` if corpus size, thresholds, or validation results changed.
- `docs/TOOL_CONTRACT.md` if `TOOLS_VERSION` or tool parameters changed.
