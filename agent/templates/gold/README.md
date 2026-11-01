# Gold template pack

Catalog entries with `gold: true` may auto-paste. Non-gold named builds clarify
(e.g. igloo, wizard tower, observatory, armory, modern house).

Bar: ground-fit (no foundation air gap), recognizable title, kid + adult aliases,
within paste budgets.

**Paste budget:** plugin `max-paste-volume` default **2,000,000** (schematic
bounding-box volume). Supports mega curated pastes (~160k+ non-air; gothic
cathedral bbox ~1.66M). Claims / player-overlap / undo still apply; claim
probes are sampled. See `SHULKR_CURATED.md` for the Shulkr mega set.

**QA grid:** `make qa-grid` pastes every catalog schematic on a footprint-aware
campus at `(20000, 120, 20000)` via console `agent-paste-at` (shelf packing by
schem width×depth + aisle; no overlap; **never teleports players**) and writes
`docs/QA_GRID.md`. In-game demote: any op with `/qa-hoe`, left-click demote /
right-click undo (`neighborhood.agent.qa`), then `make qa-apply-demotions` to
set `gold: false` in `catalog.json`. Optional overview TP is in `docs/QA_GRID.md`.

**Seed-junk twins (already `gold: false`):** `cabin_stone`, `bakery_small`,
`brewing_station`, `enchanting_room`, `storage_shed`, `fishing_hut`,
`mill_water`, `warehouse_small`, `turkey_pen_small`, `tent_camp`.

**Post-demote refill:** most basics are now non-gold. Family shopping list,
sources, and drop-folder workflow → [`docs/CURATED_REFILL.md`](../../../docs/CURATED_REFILL.md).
Live gap print: `python3 scripts/list_gold_gaps.py`.

Gold IDs (live count from `catalog.json` — was ~74 pre-demote; ~20 after hoe;
refill raises it as SchemCraft/Bloxelizer cores land). Run
`python3 scripts/list_gold_gaps.py` for the truth.

Kept after demote + first SchemCraft CC-BY refill (typical):

- Farms/pens/path: `beach_hut`, crop farms, `cow_barn_medium`, `goat_pen_small`,
  `horse_stable_small`, `rabbit_hutch_small`, `bridge_oak_short`, `dock_small`,
  `herb_garden`, `zen_garden`
- Megas: `borgital_strike_cube`, `giant_flower_house`, `gothic_cathedral`,
  `large_spruce_house`, `mossy_hobbit_hole`
- Refilled CC-BY showpieces: `blacksmith_shop`, `tavern_small`, `wizard_tower`
  (plus house/cabin/castle/treehouse/bakery/etc.). Demoted mis-maps:
  `windmill_small`, `watchtower_tall`, `lighthouse_short`, `workshop_small`
  — SchemCraft survival-house URLs were not honest basics; see
  [`docs/CURATED_REFILL.md`](../../../docs/CURATED_REFILL.md).
