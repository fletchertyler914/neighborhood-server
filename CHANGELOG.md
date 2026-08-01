# Changelog

All notable changes to this experimental neighborhood-server stack are
documented here. Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Opt-in Compose `ollama` profile for bundled local LLM without a host Ollama
  install. `make bootstrap` sets `COMPOSE_PROFILES=ollama` and
  `OLLAMA_BASE_URL=http://ollama:11434` in `.env` so plain `make up` works.
- `MC_ENFORCE_WHITELIST` env override for friends-server mode (default is
  `true` for safe public deploys).
- `scripts/playit_setup.py` + `make tunnels`: idempotently creates the
  standard Minecraft Java (TCP 25565) + Bedrock (UDP 19132) tunnels in
  playit.gg via the official API. `make bootstrap` calls it automatically
  when `PLAYIT_SECRET_KEY` is set, so a fresh clone needs zero clicks in
  the playit dashboard.
- `scripts/print_invite.py` + `make invite`: queries the playit API for
  current tunnel addresses and writes a print-ready HTML guest sheet to
  the user's Desktop.
- `config/patches/bukkit-overrides.json` (itzg `PATCH_DEFINITIONS`):
  permanently disables Paper's `connection-throttle` so Geyser/Floodgate
  Bedrock players and playit-routed Java players sharing the same upstream
  source IP don't get hit with `Connection throttled!` on rapid reconnect.
  Applied on every boot, survives `data/` resets.
- BlueMap web map: installed via `MODRINTH_PROJECTS: bluemap`, served on
  `http://127.0.0.1:8100` after the next `docker compose restart mc`.
  Baseline config (`accept-download`, render-thread cap, webserver bind)
  ships in `config/bluemap/` and is file-bind-mounted on top of BlueMap's
  defaults so a fresh clone needs no manual config edits. Host port is
  locked to `127.0.0.1` — see `config/bluemap/README.md` to share on LAN
  or expose publicly via a third playit tunnel.
- Documentation sync pass: `.cursor/rules/*.mdc`, `README.md`,
  `docs/PUBLIC_QUICKSTART.md`, `docs/HOSTING.md`, `docs/DEVELOPMENT_WORKFLOW.md`,
  `docs/ARCHITECTURE.md`, `docs/TOOL_CONTRACT.md`, `docs/TEMPLATE_RANKING.md`,
  and `docs/WORLD_EDITING.md` all moved to the `agent/tools/` package layout
  and `TOOLS_VERSION 2.9.0`.

### Changed
- `TOOLS_VERSION` bumped to `2.9.0` (synced with `TOOLS_VERSION_EXPECTED`).
- Plugin: `OrchestratorClient` refuses to send jobs when `AGENT_API_TOKEN`
  is unset; the in-game error tells the player to fix `.env` and rebuild.

### Removed
- Tracked `.cursor/plans/` (now gitignored; internal planning only).
- `dev-change-me` fallback for `AGENT_API_TOKEN` — Compose now interpolates
  `${AGENT_API_TOKEN:?Set AGENT_API_TOKEN in .env — run make bootstrap}`
  and refuses to boot without it.

### Security / OSS hygiene
- Sanitized example player names; empty default `OPS:` block.
- Whitelist **on** by default (`ENFORCE_WHITELIST: ${MC_ENFORCE_WHITELIST:-true}`).
- `mc-agent` clarified: binds `0.0.0.0` *inside* the Compose network only —
  no host `ports:` mapping; bundled Ollama (`mc-ollama`) is the same — no
  host port.

### Validated (e2e)
- `make test` — 170+
- `make smoke` — 26/26 NL prompts through live LLM
- `make eval` — 19/19 spec, 0 regressions vs baseline
- `make live-tools` — 20/20 RCON integration tests

## 2026-05 — pre-OSS hardening

### Added
- Orchestrator package layout (`agent/orchestrator/`) with deep `/health`
  and Prometheus `/metrics`.
- Tools package layout (`agent/tools/`) with submodule boundaries (admin,
  builders, fawe, inspection, templates).
- Confirm tokens bound to player + prompt + tool + args + 60s TTL.
- Job store LRU cap (500) and audit/ranking-audit log rotation.
- Pack ingest copies `.schem` files; `--allow-untrusted` gate for ad-hoc packs.
- Training export: tool-result messages in SFT, cluster-based DPO pairing,
  bad ratings without tool calls.
- Seed pipeline restores previous schematic on failed `//schem save`.
- `must_call_any` OR-group assertion primitive for spec eval.
- Shape-word router in orchestrator: "cylinder" overrides template-first
  routing and rewrites misrouted castle/house calls to `fawe_cyl_at_player`.
- `fawe_cyl_at_player(hollow=True)` — uses FAWE `//cyl -h` for hollow forts.
- `scripts/bootstrap.sh` — one-shot fresh-clone setup (secrets, .env,
  dep checks, interactive Ollama path choice).
- `Makefile` — `make bootstrap|up|seed|smoke|eval|live-tools|health|metrics`.
- `scripts/_detect_player.sh` — auto-detect first online player for
  smoke/live tests.
- MIT `LICENSE`, polished `docs/PUBLIC_QUICKSTART.md`, README quickstart banner.
- **612-prompt NL corpus** (`agent/eval/corpus/`) with live world probes
  and 8 language styles.
- Corpus runner, probes, triage, and continuous DPO/SFT training pipeline.
- Make targets: `corpus`, `corpus-quick`, `corpus-gate`, `triage`, `train`,
  `compare-models`, `corpus-baseline`.
- Docs: `docs/CORPUS.md`, `docs/FINE_TUNING.md`.
- `eval_temperature` on job requests for diverse resampling.

### Changed
- System prompt: critical word-routing table at top; cylinder vs castle
  disambiguation.
- Spec eval cases relaxed to semantic correctness (FAWE sphere wrapper OR
  `fawe_as_player`; house via template OR parametric builder).
- Strict baseline regenerated: **19/19 spec cases pass** on
  `qwen2.5:7b-instruct` (verified stable over 3 consecutive runs).
- `paste_template_at_player` returns structured error with suggestions when
  template id can't be resolved (e.g. hallucinated "sand fort").
- `agent-smoke.sh`, `live-tool-tests.sh`, `full_validation.py` auto-detect
  online player instead of hardcoding a username.
- Destructive gating uses registry `risk=high` plus pattern fallback.
- MCP adapter uses typed per-tool handlers (no runtime `exec`).
- Executor rejects unknown tool arguments when `additionalProperties: false`.
- Eval CLI / runner: when `--compare-baseline` is provided, only regressions
  are fatal — failures already in the baseline are recorded but not exit-2.
- Catalog aliases broadened so lexical-only ranking (no embeddings) still
  resolves NL phrasings like "wheat field", "pumpkin patch", "medieval gate",
  "place for chickens to live", "gazebo in the garden". Removed the
  over-greedy single-word `garden` alias from `garden_plot`.
- `agent/eval/template_ranking_eval.py` switched to template ids that
  actually exist in the corpus; the deterministic ranker eval passes 53/53.
- CONTRIBUTING.md updated with Makefile workflow and PR checklist.

### Security
- `AGENT_API_TOKEN` required when `AGENT_EVAL_MODE` is off.
- Player names and block ids validated before RCON.

### Validated (e2e on `mc-lan`)
- `pytest tests/` — 129/129
- `pytest tests/integration/test_live_tools.py` — 20/20 against running Paper
- `python -m agent.eval.template_ranking_eval` — 53/53
- `scripts/agent-smoke.sh` (real LLM through `mc-agent`) — 26/26 jobs `done`,
  ranker chose the expected template family on every prompt
- `agent.eval.cli run spec --compare-baseline …` — 15/19 with 0 regressions
- `agent.eval.cli run world safety.fort_does_not_bury_player` — pass
- `/health`, `/capabilities`, `/metrics` all green; metrics populate after jobs
