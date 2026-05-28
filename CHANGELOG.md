# Changelog

All notable changes to this experimental neighborhood-server stack are documented here.

## [Unreleased]

### Added
- `must_call_any` OR-group assertion primitive for spec eval (accepts multiple
  equally-good tool answers)
- Shape-word router in orchestrator: "cylinder" overrides template-first routing
  and rewrites misrouted castle/house calls to `fawe_cyl_at_player`
- `fawe_cyl_at_player(hollow=True)` — uses FAWE `//cyl -h` for hollow forts
- `scripts/bootstrap.sh` — one-shot fresh-clone setup (secrets, .env, dep checks)
- `Makefile` — `make bootstrap|up|seed|smoke|eval|live-tools|health|metrics`
- `scripts/_detect_player.sh` — auto-detect first online player for smoke/live tests
- MIT `LICENSE`, polished `docs/PUBLIC_QUICKSTART.md`, README quickstart banner

### Changed
- System prompt: critical word-routing table at top; cylinder vs castle disambiguation
- Spec eval cases relaxed to semantic correctness (FAWE sphere wrapper OR
  `fawe_as_player`; house via template OR parametric builder)
- Strict baseline regenerated: **19/19 spec cases pass** on `qwen2.5:7b-instruct`
  (verified stable over 3 consecutive runs)
- `paste_template_at_player` returns structured error with suggestions when
  template id can't be resolved (e.g. hallucinated "sand fort")
- `agent-smoke.sh`, `live-tool-tests.sh`, `full_validation.py` auto-detect
  online player instead of hardcoding a username
- CONTRIBUTING.md updated with Makefile workflow and PR checklist

### Validated (e2e)
- `make test` — 129/129
- `make smoke` — 26/26 NL prompts through live LLM
- `make eval` — 19/19 spec, 0 regressions vs baseline
- `make live-tools` — 20/20 RCON integration tests

### Added (prior hardening pass)
- Orchestrator package layout (`agent/orchestrator/`) with deep `/health` and `/metrics`
- Tools package layout (`agent/tools/`) with submodule boundaries for incremental split
- Confirm tokens bound to player, prompt, tool, args, and 60s TTL
- Job store LRU cap (500) and audit/ranking-audit log rotation
- Pack ingest copies `.schem` files; `--allow-untrusted` gate for ad-hoc packs
- Training export: tool-result messages in SFT, cluster-based DPO pairing, bad ratings without tool calls
- Seed pipeline restores previous schematic on failed `//schem save`
- Strict eval baseline regenerated for all spec cases

### Changed
- `TOOLS_VERSION_EXPECTED` synced to `2.8.0`
- Destructive gating uses registry `risk=high` plus pattern fallback
- MCP adapter uses typed per-tool handlers (no runtime `exec`)
- Executor rejects unknown tool arguments when `additionalProperties: false`
- Eval CLI / runner: when `--compare-baseline` is provided, only regressions
  are fatal (failures already in the baseline are recorded but not exit-2).
  This lets CI track LLM drift without forcing every refactor to also land
  a model upgrade.
- Strict baseline (`agent/eval/baseline.strict.json`) updated to the
  observed behavior of the default local model (`qwen2.5:7b-instruct`).
  Four cases are flagged `known_failure` with notes for the next
  model/prompt-strategy upgrade.
- Catalog aliases broadened so lexical-only ranking (no embeddings) still
  resolves NL phrasings like "wheat field", "pumpkin patch", "medieval gate",
  "place for chickens to live", "gazebo in the garden". Removed the
  over-greedy single-word `garden` alias from `garden_plot`.
- `agent/eval/template_ranking_eval.py` switched to template ids that
  actually exist in the corpus; the deterministic ranker eval now passes
  53/53.

### Security
- `AGENT_API_TOKEN` required when `AGENT_EVAL_MODE` is off
- Player names and block ids validated before RCON

### Validated (e2e on `mc-lan`)
- `pytest tests/` — 129/129
- `pytest tests/integration/test_live_tools.py` — 20/20 against running Paper
- `python -m agent.eval.template_ranking_eval` — 53/53
- `scripts/agent-smoke.sh` (real LLM through `mc-agent`) — 26/26 jobs `done`,
  ranker chose the expected template family on every prompt
- `agent.eval.cli run spec --compare-baseline …` — 15/19 with 0 regressions
- `agent.eval.cli run world safety.fort_does_not_bury_player` — pass
- `/health`, `/capabilities`, `/metrics` all green; metrics populate after jobs
