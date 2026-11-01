# Schematic seed → catalog ingest schema

Contract for external scrapers (e.g. `schem_scraper`) that feed
`scripts/import_seed_csv.py`. Runtime ingest is `companion/ingest_schem.py`
(same path as `make ingest-schem` and ops `/ai ingest`).

---

## Scraper CSV (input)

Default path from the other agent: `output/seed_schematics.csv`.

| Column | Required | Maps to |
| --- | --- | --- |
| `url` | **yes** | Ingest URL — SchemCraft page, Bloxelizer page/CDN, Abfielder, or **direct** `.schem` / `.zip` / `.litematic` |
| `matched_category` | **yes*** | Mapped → catalog `id` via `scripts/seed_category_map.yaml` |
| `title` | **yes** | Catalog `title` |
| `source` | no | Provenance note (site name) → author/attribution hint |
| `format_hint` | no | e.g. `schem`, `litematic`, `zip` — used for skip heuristics |
| `scraped_at` | no | Ignored by import |

\* Or pass `catalog_id` / `id` directly (wins over `matched_category`).

### Optional CSV columns (import understands these too)

| Column | Default | Notes |
| --- | --- | --- |
| `catalog_id` or `id` | from map | Exact catalog template id |
| `author` | from page / `source` | Creator name |
| `license` | from page | SPDX: `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`, `CC-BY-NC-4.0`, `CC-BY-NC-SA-4.0`, `MIT` |
| `aliases` | — | Comma-separated kid phrases |
| `gold` | `true` | Set `false` to stage without auto-paste |

### Category → catalog id (examples)

Configured in `scripts/seed_category_map.yaml` (extend as needed):

| `matched_category` | Catalog `id` |
| --- | --- |
| `windmill` | `windmill_small` |
| `sheep_pen` | `sheep_pen_medium` |
| `pig_pen` | `pig_pen_small` |
| `flower_garden` / `garden` | `garden_plot` |
| `carrot_garden` | `carrot_farm_small` |
| `hut` / `cabin` | `cabin_log` |
| `beehive` / `apiary` | `bee_apiary_small` |
| `tree` / `oak_tree` | `tree_oak_large` |
| `chicken_coop` / `coop` | `chicken_coop_small` |
| `well` | `well_village` |
| `stall` / `market_stall` | `market_stall` |
| `workshop` | `workshop_small` |
| `lighthouse` | `lighthouse_short` |
| `watchtower` | `watchtower_tall` |
| `house` / `cottage` | `house_cottage_small` |

If `matched_category` is already a catalog id (`windmill_small`), it is accepted as-is.

### Rows the importer skips

For intents in `BASIC_STRUCTURE_INTENTS` (coop, pens, stall, well, windmill,
watchtower, lighthouse, workshop, cabin, …):

- Titles matching **Ultimate / Survival Base/House/Home** (mega feature-named houses)
- **Create-mod** pack titles
License is enforced at ingest: `CC0` / `CC-BY` / `CC-BY-SA` / `CC-BY-NC` /
`CC-BY-NC-SA` / `MIT`. **CC-BY-NC is OK** for this private non-commercial
server; ingest always persists `source_url`, `license`, `author`, and
`attribution`. Prefer CC-BY when bulk-scraping. Friends Shulkr ARR needs
`--allow-arr`. ND / unknown / proprietary still rejected.

---

## Required for promote (minimum)

```
url                  # downloadable page or direct file
catalog_id           # OR matched_category mappable via seed_category_map.yaml
title                # human title for catalog + aliases seed
```

Optional: `author`, `license`, `aliases` (comma), `gold` (default true), `format_hint`.

---

## Catalog fields after ingest

Written/updated on the template row in `agent/templates/catalog.json`:

```
id, title, category, tags, aliases, schematic, footprint, max_blocks,
gold, source_url, author, license, attribution
```

Also set when present: `source_id`, `source_ref`. File lands at
`agent/templates/schematics/<id>.schem`.

---

## Import commands

```bash
# Dry-run (no writes) — validate mapping + skip rules
make import-seed-csv CSV=/path/to/schem_scraper/output/seed_schematics.csv DRY_RUN=1

# Promote matching rows
make import-seed-csv CSV=/path/to/schem_scraper/output/seed_schematics.csv

# One intent only
make import-seed-csv CSV=/path/to/seed_schematics.csv ONLY=windmill_small

# Reload companion after successful promote
make companion-reload
```

Equivalent:

```bash
PYTHONPATH=. python3 scripts/import_seed_csv.py \
  --csv /path/to/seed_schematics.csv --dry-run
```

Single URL (no CSV):

```bash
make ingest-schem URL='https://…' ID=chicken_coop_small TITLE='Small chicken coop'
```

---

## Preferred URL shapes

1. Direct `.schem` (or `.zip` containing one) — best for basics
2. [SchemCraft](https://www.schemcraft.com/) Free **CC-BY** or **CC-BY-NC** page — landmarks / furnished houses (store attribution)
3. [Bloxelizer](https://bloxelizer.com/) / Abfielder / MCBuild — **small** basics
4. Local path after browser convert (Shulkr ARR megas — manual only)

Do **not** promote Create-mod builds into gold basics. Prefer CC-BY over NC
when choosing bulk scrapes; NC is fine for one-off private-server ingest.
