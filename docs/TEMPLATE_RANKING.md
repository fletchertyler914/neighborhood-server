# Hybrid Template Ranking

Natural-language build requests (`/agent build a small chicken coop`, MCP
`paste_template_at_player`) resolve through a **deterministic hybrid ranker**
so small local models do not need to memorize snake_case template ids.

## Flow

```text
prompt → resolve_template() → confidence gate → paste_template_at_player / disambiguation
```

1. **Intent normalizer** — optional `intent_family` from orchestrator (`farm_pen`, `castle`, …).
2. **Lexical candidates** — aliases, tags, titles (word-boundary aware).
3. **Semantic candidates** — local CPU bag-of-words cosine similarity (no GPU, no vector DB).
4. **Policy reranker** — intent/size/schematic boosts with stable tie-breaks.
5. **Confidence gate** — `high` auto-select, `medium` select + disambiguation note, `low` suggestions.

Single entrypoint: `agent/templates/ranking.py` → `resolve_template(query, context)`.

## MCP / agent portability

| Tool | Role |
| --- | --- |
| `search_templates` | Inspect top candidates + confidence without building |
| `paste_template_at_player` | Build; `template_id` accepts NL or catalog id |
| `list_templates` | Browse catalog by category/tags |

All MCP clients share `agent/tools.py` and the same ranker — no hidden prompt hacks.

## Configuration

Set in `.env` (see `.env.example`). Applied to `mc-agent` in `docker-compose.yml`.

| Variable | Default | Description |
| --- | --- | --- |
| `TEMPLATE_RANKER_MODE` | `hybrid` | `hybrid` or `lexical_only` |
| `TEMPLATE_EMBEDDING_BACKEND` | `local` | `local` or `disabled` (lexical-only semantic seed) |
| `TEMPLATE_RANK_TOP_K` | `8` | Candidate pool size |
| `TEMPLATE_CONFIDENCE_HIGH` | `0.72` | Auto-select threshold |
| `TEMPLATE_CONFIDENCE_MEDIUM` | `0.45` | Select with disambiguation note |
| `TEMPLATE_RANK_W_*` | 0.55 / 0.30 / 0.15 | Lexical / semantic / policy weights |
| `TEMPLATE_RANKING_AUDIT` | `true` | Append `data/template-ranking-audit.jsonl` |

**Local MacBook** and **VPS**: same env vars; CPU-only embeddings. Use
`TEMPLATE_EMBEDDING_BACKEND=disabled` on very small instances.

## Corpus growth

```bash
# Merge sprint rows into catalog.json (target 100+)
python3 -m agent.templates.ingest --apply-corpus-sprint

# Seed missing .schem files (requires server + OP player)
python3 -m agent.templates.seed --player YourName --missing-only

# Ingest approved community packs (pack.json + license)
python3 -m agent.templates.ingest --pack-dir agent/templates/packs/my_pack --source-id neighborhood_internal
python3 -m agent.templates.ingest --ingest-packs
```

Licenses: inbound CC0 / CC-BY / CC-BY-SA / MIT only (`license_policy.yaml`).

## Observability

- **Job audit** — `routing.template_ranking` on each `/agent` job (`agent-audit.log`).
- **Ranking audit** — `data/template-ranking-audit.jsonl` (top candidates, confidence).
- **Feedback** — `/agent good` / `/agent bad` joins audit for tuning exports.

## Tests

```bash
pytest tests/test_template_ranking.py -q
python3 -m agent.eval.template_ranking_eval
```

## Rollout phases

1. **Phase 1** — Ranking API + audit logs (done).
2. **Phase 2** — Hybrid on all template traffic; lexical fallback when embeddings disabled (done).
3. **Phase 3** — Corpus 101 verified schematics, community pack ingestion (done).
4. **Phase 4** — Eval gate in CI; expand toward 250+ templates.

After Python changes: `docker compose up -d --build --no-deps mc-agent`.

## Production validation snapshot (tools_version `2.8.0`)

The most recent end-to-end pass on the live Paper server:

| Surface | Result |
| --- | --- |
| `pytest tests/` | 123 passed, 20 skipped |
| Live tool integration (`scripts/live-tool-tests.sh`) | 20/20 passed |
| Template ranking eval (`agent.eval.template_ranking_eval`) | green |
| Full world validation (`scripts/full_validation.py`) | 101/101 templates pasted via real schematics, 0 fallbacks, 59/59 supported mobs summoned |
| Real `/v1/jobs` NL smoke (26 prompts, `qwen2.5:7b-instruct`) | 26/26 routed to the expected tool |

The NL smoke set covers houses (cabin, two-story, tavern, cottage, treehouse,
apartment), bridges (wood, stone, rope), castles/towers (castle, watchtower,
wizard tower, fortress, lighthouse), animal pens (chicken coop, "place for
chickens to live", horse stable), nature/decor (oak tree, fountain, hedge maze,
windmill), mob summons (chicken/horse/sheep), and world ops (time, weather).
