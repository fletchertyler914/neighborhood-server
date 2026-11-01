# Template library workflow

The elite builder stack stores reusable FAWE schematics plus metadata so
The in-game `/agent` sidekick pastes high-quality structures instead of guessing
parametric shapes.

## Layout

| Path | Role |
| --- | --- |
| `agent/templates/catalog.json` | Allowlisted ids, aliases, footprint, provenance, `fallback` / `fallback_steps` |
| `agent/templates/schematics/*.schem` | Source schematics (git) |
| `agent/templates/sources.yaml` | Community source allowlist (pinned refs) |
| `agent/templates/license_policy.yaml` | Permissive inbound SPDX list |
| `agent/templates/ingest.py` | Pack ingest + gold corpus merge + attribution |
| `agent/templates/seed.py` | Sandbox fallback builds → schematics |
| `agent/templates/publish.py` | CC-BY outbound pack bundles |
| Container: `/data/plugins/FastAsyncWorldEdit/schematics/neighborhood/` | Runtime paste target (compose volume) |

**Paste volume cap:** Paper plugin `max-paste-volume` defaults to **2,000,000**
(bounding-box cells). Mega curated gold (gothic cathedral ~155k non-air /
~1.66M bbox) pastes under that cap; raise only with care.

Catalog: **100+** templates (gold + corpus sprint entries). Natural-language
selection uses the hybrid ranker — see `docs/TEMPLATE_RANKING.md`. See also
`docs/TEMPLATE_INGESTION_POLICY.md` and `docs/COMMUNITY_PUBLISHING.md`.

## In-game publish

1. Select with WorldEdit (`//wand`, `//pos1`, `//pos2`).
2. Ask the agent to save: e.g. `/agent save selection as template my_shack tags farm,wood`.
3. `create_template_from_selection` runs `//copy`, `//schem save`, copies the
   file into the repo, and appends `catalog.json` (`category: community`).
4. Commit `catalog.json` + `schematics/my_shack.schem` after review.

## Git-curated sharing

1. Add or edit entries in `catalog.json` (title, tags, `max_blocks`, `follow_up`).
2. Drop `.schem` files under `agent/templates/schematics/`.
3. `docker compose up -d mc` remounts schematics; `paste_template_at_player`
   calls `ensure_schematic_on_server` if the file is missing in-container.

## Curated gold refill (post-demote)

After QA demotions, refill high-frequency kid cores with legitimate community
`.schem` files (not seed-junk twins). Shopping list, sources (Bloxelizer,
SchemCraft, Shulkr, Abfielder, …), and drop-folder workflow:

→ [`docs/CURATED_REFILL.md`](CURATED_REFILL.md)

```bash
python3 scripts/list_gold_gaps.py --prio P0
```

## Manual QA grid (keep / demote)

Paste **all** catalog schematics on a remote pad far from spawn, then fly the
grid and mark junk for demote. Community scrape should wait until QA flags
bad assets — do not mass-ingest replacements first.

```bash
# Console-only — does not teleport or require any online player.
make qa-grid
```

- Pad origin: `(20000, 120, 20000)` — footprint-aware shelf packing (schem
  width×depth + aisle; no cell overlap; megas get exclusive rects)
- Populate uses `agent-paste-at` (FAWE at fixed coords); **never moves players**
- Overview / ground TP: see [`docs/QA_GRID.md`](QA_GRID.md) (optional viewing only)
- Index: [`docs/QA_GRID.md`](QA_GRID.md) (row/col → id/title/gold + stand + reserved)
- Demote: wooden hoe in-game, then `make qa-apply-demotions` (see `agent/templates/gold/README.md`)
- Full world check (templates + mobs): `make full-validation`

## Seed missing schematics

When a catalog entry has `fallback` but no `.schem` in repo:

```bash
export AGENT_SEED_PLAYER=YourJavaName
export AGENT_SEED_SANDBOX_X=9300 AGENT_SEED_SANDBOX_Y=90 AGENT_SEED_SANDBOX_Z=9300
./scripts/seed-templates.sh --missing-only --limit 10
```

Requires a running `mc-lan` container and an opped seed player teleported away
from builds. See `docs/DETERMINISTIC_VALIDATION.md`.

## Ingest community packs

```bash
python3 -m agent.templates.ingest --pack-dir ./path/to/pack --source-id my_pack
python3 -m agent.templates.ingest --attribution
```

## Routing rules (orchestrator)

- Named structure without explicit dimensions → `paste_template_at_player`.
- Custom materials in prompt (e.g. spruce fence) → parametric pen/house tools.
- Prompts with `21x21`, `radius N`, `exactly N blocks` → parametric tools.
- Misrouted `build_house` / `build_cylinder` for coops/castles are rewritten
  before execution; routing metadata is stored on the audit entry for feedback
  export (`intent_family`, `selected_template_id`, `source_id`, `content_hash`,
  `rewrite_applied`, `fallback_reason`).

## Player feedback → training

After a build, `/agent good` or `/agent bad <why>` copies routing fields from
the audit log into `data/agent-feedback.jsonl`. Export SFT/DPO pairs with:

```bash
python -m agent.training feedback --format sft --out datasets/sft.jsonl
```

Routing fields in `meta` help fine-tune template vs parametric tool choice.
