# Curated gold refill (post-demote)

After QA demotions, catalog gold collapsed from ~74 → **20**. Seed-schema
junk twins and lookalike boxes were correctly demoted; high-frequency kid asks
(house, coop, barn, stall, castle, …) clarified or fell back instead of
auto-pasting. SchemCraft CC-BY refill then raised gold, but several
**basics** were wrong (feature-word megas, not the structure kids asked for).
Those are demoted again — see [Demoted SchemCraft mis-maps](#demoted-schemcraft-mis-maps).
This doc is the family shopping list + workflow to finish refill with
**legitimate** community `.schem` files.

Print the live gap list anytime:

```bash
make gold-gaps
make gold-gaps PRIO=P0          # week-1 cores only
python3 scripts/list_gold_gaps.py --prio P0
```

**Weekly ops:** `make companion-gaps-export` (or `make companion-triage`) — review
`data/companion-gaps-export.jsonl` for real unfulfilled asks (`clarify` /
`unresolved` / `refuse` / `failed` / `ingest`) and prioritize catalog refill
from those prompts.

License gate (inbound): `CC0-1.0` · `CC-BY-4.0` · `CC-BY-SA-4.0` ·
`CC-BY-NC-4.0` · `CC-BY-NC-SA-4.0` · `MIT`
(`agent/templates/license_policy.yaml`). **CC-BY-NC is OK** for this private
non-commercial neighborhood server when `source_url` / `author` / `license` /
`attribution` are stored on the catalog entry. **Reject ND / unknown /
paywalled.** Prefer CC-BY (or CC0/MIT) when choosing bulk scrapes.
Friends-server curated ARR (Shulkr megas) remains an explicit exception —
document provenance; do not treat ARR as the default for basics.

Runtime paste format: **Sponge `.schem`** (FAWE). Prefer native `.schem`
downloads. `.litematic` / `.nbt` / `.mcstructure` must be converted first
([Bloxelizer converter](https://bloxelizer.com/converter),
[schemcraft](https://www.schemcraft.com/), [shulkr](https://www.shulkr.com/),
or FAWE).

---

## Sourcing strategy (read this first)

| Role | Sources | Examples |
| --- | --- | --- |
| **Landmarks / showpieces / furnished bases** | SchemCraft (CC-BY Free), Shulkr (manual ARR megas) | castle, tavern, blacksmith, wizard tower, treehouse, cottage house, bakery, library |
| **Basics / simple structures** | Bloxelizer · Abfielder · MCBuild · PhantomMarket with **small block-count filters** (pipeline `max_blocks_basic` ≈ 40k); or keep parametric `place_shape` when no honest schem | windmill, well, coop, pens, stall, simple cabin, workshop, short lighthouse, watchtower, garden plot |

**Why:** SchemCraft “Ultimate … Survival Base/House” listings often name a
feature (windmill, lighthouse, workshop) but are full furnished homes. Kids
asking “build me a windmill” get a fantasy house — wrong product.

**Pipeline deny (enforced in `scripts/schem_pipeline/taxonomy.py`):** for
`BASIC_STRUCTURE_INTENTS`, reject titles matching *survival base/house/home*
or *ultimate … base/house* even if a feature keyword hits. Do **not** map
“Ultimate X Survival House” → windmill / well / coop / pens / stall / cabin /
workshop / lighthouse / watchtower.

**Honest basics approach when SchemCraft fails:**

1. Search Bloxelizer / MCBuild / Abfielder / PhantomMarket; sort by block count;
   prefer ≤ ~15–40k non-air and a silhouette that *is* the ask.
2. If nothing honest exists, leave `gold: false` and rely on parametric
   `place_shape` / tool fallbacks (coop→pen, well→decoration, etc.).
3. Do **not** promote a mega survival house just to fill the gap.

---

## Demoted SchemCraft mis-maps

Set `gold: false` (schem files kept for reference / later replace). **No QA pad
regen** for this pass.

| Catalog id | Bad source | Why demoted |
| --- | --- | --- |
| `windmill_small` | [fantasy-windmill-survival-house](https://www.schemcraft.com/schematics/fantasy-windmill-survival-house) | Fantasy **house** with a windmill feature — not a windmill (**refilled** — see seed list below) |
| `watchtower_tall` | [ultimate-medieval-watchtower-survival-base](https://www.schemcraft.com/schematics/ultimate-medieval-watchtower-survival-base) | Mega **survival base**, not a simple watchtower |
| `lighthouse_short` | [ultimate-lighthouse-keeper-survival-base](https://www.schemcraft.com/schematics/ultimate-lighthouse-keeper-survival-base) | Lighthouse-keeper **survival base**, not a short lighthouse |
| `workshop_small` | [ultimate-super-smelter-workshop-survival-base](https://www.schemcraft.com/schematics/ultimate-super-smelter-workshop-survival-base) | Super-smelter **survival base**, not a small workshop |

Re-fill remaining demotions from small-filter sources or leave non-gold + parametric fallback.

---

## Remaining gold (keep)

| id | Role |
| --- | --- |
| `beach_hut` | small coastal house |
| `berry_farm_small` · `carrot_farm_small` · `melon_farm_small` · `potato_farm_small` · `pumpkin_farm_small` · `wheat_farm_small` | crop farms (kept) |
| `cow_barn_medium` · `goat_pen_small` · `horse_stable_small` · `rabbit_hutch_small` | animal pens (kept) |
| `bridge_oak_short` · `dock_small` | water / path (kept) |
| `herb_garden` · `zen_garden` | gardens (kept) |
| `mossy_hobbit_hole` · `giant_flower_house` · `large_spruce_house` · `gothic_cathedral` · `borgital_strike_cube` | curated megas / landmark |
| `barn_red_large` | Bloxelizer barn+silo (honest basic) |
| `windmill_small` | Bloxelizer windmill (honest basic, ~917 blocks) |
| `sheep_pen_medium` | Abfielder Animal Pen (friends ARR, 13×5×13 / 280 blocks) |
| `garden_plot` | Abfielder Easy flower farm (friends ARR, 7×5×11 / 166 blocks) |
| `watchtower_tall` | Bloxelizer watchtower-2 (~476 blocks) |
| `workshop_small` | Bloxelizer smelter (~214 blocks) |
| `tree_oak_large` | Bloxelizer Custom oak tree (~130 blocks) |
| `blacksmith_shop` · `tavern_small` · `wizard_tower` · `house_cottage_small` · `cabin_log` · `treehouse_oak` · `castle_small_keep` · `cottage_medium` · `bakery_small` · `fishing_hut` · `library_small` | SchemCraft showpieces / furnished bases (house-shaped intents OK) |

**Still weak for kid play until refilled honestly:** coop, pig pen, stall,
well, short lighthouse, bee house. Cabin/house SchemCraft fills are
showpiece-sized — prefer smaller replacements over time for “tiny cabin” asks.

---

## High-value gaps

### P0 — refill this week (gameplay frequency)

| Catalog id | Kid ask | Notes |
| --- | --- | --- |
| `house_cottage_small` | house / cottage / tiny house | SchemCraft showpiece OK; prefer smaller if found |
| `cabin_log` | log cabin | Prefer small Bloxelizer/MCBuild; survival-house megas denied for basics |
| `chicken_coop_small` | chicken coop / hen house | **Basic** — Bloxelizer / MCBuild only; no survival-house maps |
| `barn_red_large` | barn / red barn | Already gold (Bloxelizer) — keep |
| `pig_pen_small` | pig pen | **Basic** — still open (do not twin Animal Pen) |
| `sheep_pen_medium` | sheep pen | **Gold** — Abfielder Animal Pen (ARR exception) |
| `bee_apiary_small` | bee house | **Basic** — skip Create-mod; no vanilla small hit yet |
| `garden_plot` | garden / flower garden | **Gold** — Abfielder Easy flower farm (ARR); PMC #15493 login-walled |
| `market_stall` | market / shop stall | **Basic** — tiny footprint (Bloxelizer marketplace too large) |
| `blacksmith_shop` | blacksmith | Showpiece OK (already gold) |
| `tavern_small` | tavern | Showpiece OK (already gold) |
| `workshop_small` | workshop | **Gold** — Bloxelizer [smelter](https://bloxelizer.com/schematics/smelter) (~214) |
| `castle_small_keep` | little castle | Landmark OK |
| `watchtower_tall` | watchtower | **Gold** — Bloxelizer [watchtower-2](https://bloxelizer.com/schematics/watchtower-2) |
| `lighthouse_short` | lighthouse | **Basic** — demoted keeper base; Bloxelizer convert failed |
| `windmill_small` | windmill | **Gold** — Bloxelizer [windmill](https://bloxelizer.com/schematics/windmill) |
| `treehouse_oak` | treehouse | Showpiece OK |
| `well_village` | village well | **Basic** — tiny builds only |

### P1 — next (variants + junk-twin replacements)

| Catalog id | Kid ask | Notes |
| --- | --- | --- |
| `cottage_medium` | medium / bigger cottage | pair with small cottage |
| `modern_house_flat` | modern house | clarify today |
| `igloo_small` | igloo | clarify today |
| `bridge_rope` | rope bridge | oak bridge already gold |
| `bridge_stone_long` | stone bridge | |
| `pier_long` | long pier | dock kept |
| `fishing_hut` | fishing hut | showpiece-sized SchemCraft OK for now |
| `bakery_small` | bakery | showpiece-sized SchemCraft OK for now |
| `storage_shed` | shed / storage | **Basic** — replace seed junk |
| `mill_water` | water mill | **Basic** — filter size |
| `inn_small` | inn | |
| `church_small` | church | |
| `library_small` | library | showpiece OK |
| `wizard_tower` | wizard tower | landmark OK (already gold) |
| `greenhouse_small` | greenhouse | |
| `fountain_small` | fountain | |
| `gazebo_oak` | gazebo | |
| `playground_small` | playground | |
| `campground` | camp / campground | |
| `sugarcane_farm_small` | sugarcane farm | crop set incomplete |
| `cabin_stone` | stone cabin | prefer distinct schem **or** alias→`cabin_log` |

### P2 — nice-to-have / lower frequency

`townhouse_2story`, `desert_house_small`, `mushroom_house`, `chicken_coop_large`,
`stable_large`, `pig_pen_large`, `kelp_farm_small`, `mushroom_farm_dark`,
`silo_grain`, `bridge_wood_suspension`, `warehouse_small` (junk twin),
`gatehouse`, `guard_post`, `wooden_palisade`, `picnic_area`, `bench_row`,
`lamp_post_iron`, `brewing_station`, `enchanting_room` (junk twins — only if
genuinely distinct rooms).

### Skip / deprioritize

- Parametric trees (`tree_*`) unless a kid-loved unique tree shows up.
- Redstone AFK farms (Shulkr Fiction pack) — wrong product for `/agent build me a ___`.
- Mega “Ultimate … Survival Base/House” for **basics** — pipeline rejects these.
  Landmarks/showpieces may still use SchemCraft megas under paste budgets
  (bbox ≤ 2M). Prefer ≤ ~40k non-air for basics.

---

## Core refill shopping list (~32 intents)

Prioritized for one family week. Search queries are what to type on the sites
below. Candidate links are **optional starters** — always re-check license +
kid-fit + **honest silhouette** before drop.

| # | Intent / catalog id | Search queries | Candidate / approach |
| ---: | --- | --- | --- |
| 1 | House → `house_cottage_small` | `starter house`, `small cottage`, `oak house` | SchemCraft showpiece OK: [Fantasy Medieval Survival House](https://www.schemcraft.com/schematics/fantasy-medieval-survival-house) — or smaller from Bloxelizer |
| 2 | Cabin → `cabin_log` | `log cabin`, `wood cabin` | **Basic** — Bloxelizer / Abfielder / MCBuild, small filter |
| 3 | Coop → `chicken_coop_small` | `chicken coop`, `hen house`, `chicken pen` | **Basic** — Bloxelizer + Minecraft-Schematics Farms |
| 4 | Barn → `barn_red_large` | `red barn`, `barn` | Already gold (Bloxelizer barn+silo) |
| 5 | Pig pen → `pig_pen_small` | `pig pen`, `pig sty` | **Basic** — small enclosure |
| 6 | Sheep pen → `sheep_pen_medium` | `sheep pen`, `sheep enclosure` | **Basic** |
| 7 | Bee house → `bee_apiary_small` | `bee house`, `apiary` | **Basic** |
| 8 | Garden → `garden_plot` | `flower garden`, `garden plot` | **Basic** — plot, not estate |
| 9 | Stall → `market_stall` | `market stall`, `vendor booth` | **Basic** — tiny footprint |
| 10 | Blacksmith → `blacksmith_shop` | `blacksmith`, `forge` | Showpiece OK (already gold) |
| 11 | Tavern → `tavern_small` | `tavern`, `pub` | Showpiece OK (already gold) |
| 12 | Workshop → `workshop_small` | `workshop`, `carpenter shop`, `tool shed` | **Basic** — reject smelter survival bases |
| 13 | Castle → `castle_small_keep` | `small castle`, `keep` | Landmark OK |
| 14 | Watchtower → `watchtower_tall` | `watchtower`, `guard tower` | **Basic** — small tower only; no survival-base maps |
| 15 | Lighthouse → `lighthouse_short` | `lighthouse`, `lighthouse tower` | **Basic** — short tower; no keeper-base maps |
| 16 | Windmill → `windmill_small` | `windmill`, `flour mill` | **Basic** — real mill silhouette; **not** “windmill survival house” |
| 17 | Treehouse → `treehouse_oak` | `treehouse`, `tree house` | Showpiece OK |
| 18 | Well → `well_village` | `village well`, `wishing well` | **Basic** — Abfielder / MCBuild tiny builds |
| 19 | Medium cottage → `cottage_medium` | `medium cottage`, `family cottage` | Showpiece OK |
| 20 | Modern house → `modern_house_flat` | `modern house`, `modern flat` | Kid-safe; avoid glass megavillas |
| 21 | Igloo → `igloo_small` | `igloo`, `snow house` | **Basic** |
| 22 | Rope bridge → `bridge_rope` | `rope bridge`, `vine bridge` | **Basic** |
| 23 | Stone bridge → `bridge_stone_long` | `stone bridge`, `arch bridge` | **Basic** |
| 24 | Pier → `pier_long` | `pier`, `long pier` | Dock already gold |
| 25 | Fishing hut → `fishing_hut` | `fishing hut`, `fisherman cottage` | Showpiece-sized OK |
| 26 | Bakery → `bakery_small` | `bakery`, `bread shop` | Showpiece-sized OK |
| 27 | Shed → `storage_shed` | `storage shed`, `garden shed` | **Basic** — small only |
| 28 | Water mill → `mill_water` | `water mill`, `watermill` | **Basic** — filter size |
| 29 | Wizard tower → `wizard_tower` | `wizard tower`, `mage tower` | Landmark OK (already gold) |
| 30 | Greenhouse → `greenhouse_small` | `greenhouse`, `glass garden` | **Basic** |
| 31 | Fountain → `fountain_small` | `fountain`, `plaza fountain` | **Basic** |
| 32 | Playground → `playground_small` | `playground`, `swing set` | Kid-appropriate only |

---

## Sources (curated — no mass scrape)

### Best for basics (small filters)

| Source | Why | Notes |
| --- | --- | --- |
| [Bloxelizer](https://bloxelizer.com/schematics) | Filter size / block count / flavor / category + 3D preview | Sort by **Block Count**; `/ai ingest` auto-converts CDN `.litematic` → `.schem`. Undeclared license → **CC-BY-4.0** (still stores `source_url`) |
| [MCBuild](https://mcbuild.org/schematics/) | 10K+ buildings; houses / farms / towers | Prefer small category hits |
| [Abfielder](https://abfielder.com/) | Free schematics, often `.schem` + `.litematic` | Prefer free `.schem`; skip paid store unless license clear |
| [PhantomMarket](https://market.phantom-node.com/) | `.litematic` / `.schem` + [3D render](https://market.phantom-node.com/tools/render) | Good for tiny wells / stalls / coops |

### Best for landmarks / furnished showpieces

| Source | Why | Notes |
| --- | --- | --- |
| [schemcraft.com](https://www.schemcraft.com/) | Free pages often CC-BY-4.0 or CC-BY-NC — **NC OK** with attribution stored | Use for houses, taverns, castles — **not** for windmill/well/coop basics |
| [shulkr.com](https://www.shulkr.com/schematics) | Small browse set; good 3D; many ARR | Friends curated megas only; manual |

### Community bigger / mixed

| Source | Why |
| --- | --- |
| [Minecraft-Schematics.com](https://www.minecraft-schematics.com/) | Large archive; check license per page |
| [Planet Minecraft](https://www.planetminecraft.com/) (schematics tag) | Huge; hand-pick only |
| [Schemat.io](https://schemat.io/) | Tags + 3D viewer |

**SchemCraft tip:** “Free” pages may be **CC-BY-4.0** or **CC-BY-NC-4.0**.
Both are allowed for this private server; ingest always stores `source_url` +
`attribution`. Prefer CC-BY when bulk-scraping. Still reject ND / unknown /
ARR (unless friends Shulkr override). Title check: if it says *Survival
Base/House* and the catalog id is a basic (windmill, coop, well, …), **skip**.

---

## One-command ingest (Phase 1)

Prefer this over hand-dropping files + hand-editing `catalog.json`.
Implementation is shared: `companion/ingest_schem.py` (CLI + in-game ops route).

```bash
# Direct .schem / .zip URL (basics: prefer Bloxelizer/MCBuild)
make ingest-schem URL='https://example.com/coop.schem' ID=chicken_coop_small

# SchemCraft page — landmarks / furnished houses only
make ingest-schem \
  URL='https://www.schemcraft.com/schematics/fantasy-medieval-survival-house' \
  ID=house_cottage_small

# Local file (Shulkr browser export, Bloxelizer converter output, …)
make ingest-schem \
  URL='/path/to/cabin.schem' \
  ID=cabin_log \
  SOURCE_URL='https://www.shulkr.com/schematics/…' \
  ALLOW_ARR=1

# Reload catalog in mc-agent only (no Paper bounce)
make companion-reload
```

What it does: download → extract zip if needed → write
`agent/templates/schematics/<id>.schem` → upsert catalog gold + aliases from
title words + footprint/`max_blocks` from NBT + provenance (best-effort from
page HTML / Shulkr API). Prints id, phrases, and the reload hint.

**FAWE needs `.schem`.** `.litematic` converts in-process via
`scripts/schem_pipeline/convert.py` (`litemapy` in the `mc-agent` image; optional
CLI fallbacks `litematica-cli` / `schematic-converter` if on PATH).
Shulkr *pages* serve proprietary `.shulkr` builds (browser WASM → `.schem`) —
download `.schem` in the UI, then ingest the local file with `SOURCE_URL` +
`ALLOW_ARR=1` for friends curated ARR. **Do not scrape Shulkr** — &lt;30 megas,
manual only.

Batch (Phase 1.5): edit `scripts/ingest_shopping_list.yaml` (fill `url:`), then:

```bash
make ingest-shopping                 # skip null urls
make ingest-shopping ONLY=wizard_tower
make ingest-shopping RELOAD=1        # companion-reload at end
make ingest-shopping DRY_RUN=1
```

### In-game ops ingest (deterministic)

Ops with `neighborhood.agent.ingest` (default: op) or `neighborhood.agent.qa`:

```
/ai ingest https://www.schemcraft.com/schematics/<slug>
/ai ingest https://bloxelizer.com/schematics/<slug> Small Windmill
/ai ingest <url> as my_catalog_id
/ai ingest <url> as my_catalog_id Friendly Title
/ai add schem https://www.schemcraft.com/schematics/<slug>
/ai add template https://bloxelizer.com/schematics/<slug> as chicken_coop_small
```

- Allowlist: `schemcraft.com`, `bloxelizer.com`, `shulkr.com`, direct `.schem`/`.zip`
- Kids without permission: *"Only ops can add schematics. Ask an adult/op…"*
- Bad host (ops): *"I can only ingest SchemCraft, Bloxelizer, Shulkr, or a direct .schem/.zip link."*
- Bloxelizer: API slug → CDN `.litematic` → Sponge `.schem` (`Schematic` root). Undeclared license defaults to **CC-BY-4.0**; `source_url` always stored.
- Runs **in-process** (`companion.ingest_schem.ingest_url`) — no shell
- Reloads catalog in-memory after success; replies with id / title / try phrases
- Live smoke as **firecrab93 only** (`agent-as`). No player TP.

Needs: `make companion-deploy` (or rebuild mc-agent + plugin) so mounts are
writable (`catalog.json` + `schematics/`) and `nbtlib` + `litemapy` are in the image.

### Offline scrape seed (same backbone)

`scripts/schem_pipeline/` → download/convert → `companion.ingest_schem.ingest_url`.
Bloxelizer preferred for basics; SchemCraft for landmarks. Keyword match
required; **survival base/house titles denied for P0 basics**. Shulkr not
scraped. **No QA pad regen until gold seed is settled.**

```bash
make gold-gaps PRIO=P0
make schem-pipeline-sample                 # ~20 candidates, stage only
make schem-pipeline-sample PROMOTE=1       # best keyword match → gold
# single URL (CLI uses same module as /ai ingest):
make ingest-schem URL='https://…' ID=<catalog_id>
make companion-reload                      # after CLI; in-game reloads itself
```

Live ops smoke (firecrab93 only):  
`./mc.sh cmd 'agent-as firecrab93 ingest https://… as <id>'`

### External scraper CSV → ingest

If another agent produces `schem_scraper/output/seed_schematics.csv`
(`title,url,source,matched_category,format_hint,scraped_at`), import with:

```bash
make import-seed-csv CSV=/path/to/seed_schematics.csv DRY_RUN=1
make import-seed-csv CSV=/path/to/seed_schematics.csv
make companion-reload
```

Column mapping + skip rules (Create-mod / NC / mega survival-house for
basics): **[`docs/SCHEM_INGEST_SCHEMA.md`](SCHEM_INGEST_SCHEMA.md)**.
Category → catalog id map: `scripts/seed_category_map.yaml`.

---

## Family workflow (this week)

1. `make gold-gaps PRIO=P0` — see open cores.
2. **Basics** → Bloxelizer / MCBuild / Abfielder / PhantomMarket (small block count).
   **Showpieces** → SchemCraft CC-BY. Shulkr = megas only (manual).
3. Preview + license + silhouette check (title must *be* the ask).
4. Seed: pipeline `PROMOTE=1` and/or `/ai ingest <url> as <id>` / `make ingest-schem`.
5. Paste-test as **firecrab93 only**. QA strip later — not until seed is done.
   **Do not wipe/rebuild the QA pad** while re-sourcing basics.

---

## Easy-win SchemCraft starters (showpieces)

Verified Free + **CC-BY-4.0** (preferred) or CC-BY-NC with attribution.
Zip download works without login (`…/schematics/<slug>/download`). Suitable
for **landmarks / furnished bases** only — not for demoted basics above.

### Still wired (gold + `.schem` replaced)

| Catalog id | URL | ~blocks |
| --- | --- | --- |
| `wizard_tower` | https://www.schemcraft.com/schematics/ultimate-enchanted-wizard-tower-survival-base | 32k |
| `tavern_small` | https://www.schemcraft.com/schematics/grand-medieval-tavern-inn | 45k |
| `blacksmith_shop` | https://www.schemcraft.com/schematics/medieval-blacksmith-survival-house | 57k |
| `house_cottage_small` | https://www.schemcraft.com/schematics/fantasy-medieval-survival-house | 39k |
| `cabin_log` | https://www.schemcraft.com/schematics/ultimate-spruce-starter-survival-house | 58k |
| `treehouse_oak` | https://www.schemcraft.com/schematics/ultimate-blossom-treehouse-survival-base | 65k |
| `castle_small_keep` | https://www.schemcraft.com/schematics/ultimate-fantasy-starter-castle-house | 107k |
| `fishing_hut` | https://www.schemcraft.com/schematics/ultimate-medieval-fisherman-cottage-survival-base | 73k |
| `bakery_small` | https://www.schemcraft.com/schematics/ultimate-medieval-bakery-survival-house | 61k |
| `cottage_medium` | https://www.schemcraft.com/schematics/ultimate-fairy-tale-survival-cottage | 63k |
| `library_small` | https://www.schemcraft.com/schematics/ultimate-player-favorite-bookstore-cafe-survival-house | 84k |

### Demoted (do not re-promote these URLs)

| Catalog id | Bad URL | Reason |
| --- | --- | --- |
| `windmill_small` | fantasy-windmill-survival-house | house ≠ windmill |
| `watchtower_tall` | ultimate-medieval-watchtower-survival-base | survival base ≠ tower |
| `lighthouse_short` | ultimate-lighthouse-keeper-survival-base | survival base ≠ lighthouse |
| `workshop_small` | ultimate-super-smelter-workshop-survival-base | smelter base ≠ workshop |

Old seed junk kept under `agent/templates/schematics/_seed_bak/` (not for paste).
**Selective QA later:** paste only new honest ids via `make qa-refill ONLY=…` —
do **not** re-wipe cathedral / hobbit / flower / spruce keepers.

### Still open P0 basics (need honest small schems)

`chicken_coop_small` · `pig_pen_small` · `bee_apiary_small` · `market_stall` ·
`well_village` · `lighthouse_short`

Honest keeps: `barn_red_large` · `windmill_small` · `watchtower_tall` ·
`workshop_small` (Bloxelizer); `sheep_pen_medium` · `garden_plot` (Abfielder
friends ARR); `tree_oak_large` (Bloxelizer). Showpiece keeps listed above.

External scraper CSV → `make import-seed-csv CSV=…` —
[`docs/SCHEM_INGEST_SCHEMA.md`](SCHEM_INGEST_SCHEMA.md).

---

## Basics seed list (validated URLs → catalog)

Handed seed table → ingest via `companion/ingest_schem.py` / `make ingest-schem`
(litematic → schem via `scripts/schem_pipeline/convert.py`, varint-safe for
palettes &gt; 127). **No QA pad wipe.**

### Landed (gold)

| Catalog id | Source URL | ~blocks | License notes |
| --- | --- | --- | --- |
| `windmill_small` | https://bloxelizer.com/schematics/windmill | 917 | Undeclared on site; catalogued `CC-BY-4.0` (same convention as barn) |
| `sheep_pen_medium` | https://abfielder.com/Products/ProductDetails.php?id=4337 (Animal Pen) | 280 | Site ARR — friends-server exception (`allow_arr`) |
| `garden_plot` | https://abfielder.com/Products/ProductDetails.php?id=3219 (Easy flower farm) | 166 | Site ARR — friends-server exception; decorative PMC #15493 login-walled |
| `watchtower_tall` | https://bloxelizer.com/schematics/watchtower-2 | 476 | Undeclared → `CC-BY-4.0` convention |
| `workshop_small` | https://bloxelizer.com/schematics/smelter | 214 | Undeclared → `CC-BY-4.0` convention (small smelter, not SchemCraft mega) |
| `tree_oak_large` | https://bloxelizer.com/schematics/custom-oak-tree | 130 | Undeclared → `CC-BY-4.0` convention; one oak only (not Daniye 132-pack) |

### Skipped / failed from the same seed table

| Intent | URL / note | Why |
| --- | --- | --- |
| `bee_apiary_small` | CreateMod beehive-300 | Create-mod dependent — skip |
| `bee_apiary_small` | PMC beehive tag | No clear vanilla small decorative download found |
| Sheep | HUGE SHEEP FARM (Abfielder #2520) | Mega farm — skip |
| Sheep | Sheep Farm #2433 | Larger farm; Animal Pen preferred |
| Garden | Flower #15493 | Page OK; `/download/` redirects to login |
| Carrot | Automatic Carrot Farm / auto crop farms | Kept existing gold `carrot_farm_small` seed |
| Cabin / hut | PMC / forum hut listings | Optional; SchemCraft cabin already gold |
| Trees | Daniye 132-pack / Mr Wizz pack | Packs skipped; one oak promoted |
| PMC medieval windmill | Cloudflare / blocked from CLI | Bloxelizer windmill used instead |

---

## Related docs

- [`docs/SCHEM_INGEST_SCHEMA.md`](SCHEM_INGEST_SCHEMA.md) — scraper CSV ↔ catalog ingest contract
- [`docs/TEMPLATES.md`](TEMPLATES.md) — library layout + QA grid
- [`docs/TEMPLATE_INGESTION_POLICY.md`](TEMPLATE_INGESTION_POLICY.md) — SPDX rules
- [`agent/templates/gold/README.md`](../agent/templates/gold/README.md) — gold bar
- [`agent/templates/gold/SHULKR_CURATED.md`](../agent/templates/gold/SHULKR_CURATED.md) — mega ARR set
- [`docs/QA_GRID.md`](QA_GRID.md) — remote pad map
