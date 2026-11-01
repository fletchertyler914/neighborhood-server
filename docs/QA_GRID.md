# Template QA grid

Remote paste pad for keep/demote review. Far from spawn; does not wipe the world.

## How to view

- First cell stand: `20056 120 20002`
- Footprint-aware shelf packing: **101** shelves, row budget **400**, aisle **4** (span ~400×1276; bounds `20000,20000`..`20399,21275`)
- Each cell reserves schem width×depth + margin; next cell starts after prior extents (wrap by max depth in the shelf). No overlap.
- Artificial pad at Y=120 (stone/8 + grass; void Y=64..277, border 72)
- Pasted: **39/39** ok · **27** world-verified · **39** gold
- Populate mode: **console `agent-paste-at`** (no player; does **not** teleport anyone). Operator label: `console`

**Populate never moves players.** `make qa-grid` pastes via console FAWE at fixed stand coords. You can keep playing at spawn while it runs.

World verification counts non-air **above** the grass pad. Grass pad blocks alone do not count.

### Teleport (viewing only — optional)

Air overview (one glance):

```
/tp @s 20199 204 20637
```

Ground / first cell:

```
/tp @s 20056 120 20002
```

From host:

```bash
./mc.sh cmd "tp <your-name> 20199 204 20637"
```

BlueMap: open the map near those coords, then **Update Map** / refresh tiles if the pad still looks like the old mountain cut.

Each stand has an oak sign: **title** / **template id** / **★ gold** (or blank) — plain text, not JSON.

Re-label without re-paste: `make qa-resign-signs`.

## Mark fails (in-game demote)

**Any op** (`neighborhood.agent.qa`, default: op) — split review across ops.
Each demote/promote logs `player` in `qa-demotions.jsonl`.

1. Get a hoe: `/qa-hoe` (or `/agent qa-hoe`).
2. **Left-click** any block on a paste → chat confirms `Demoted <id> (was gold)` or `Already demoted`.
3. **Right-click** with the same hoe to **re-promote** / undo demote.
4. Demotions append to `data/plugins/NeighborhoodAgent/qa-demotions.jsonl` (survives restart).
5. Apply to catalog: `make qa-apply-demotions` (sets `gold: false`, restarts `mc-agent`).

Give the hoe (any op name — only when reviewing):

```
/qa-hoe
/give <op-name> wooden_hoe 1
```

Or from host: `./mc.sh cmd "give <op-name> wooden_hoe 1"`.

Live agent tests (`agent-as`, scripted TP) stay firecrab93-only — human QA demote is any op.

Do **not** mass-scrape replacements until QA identifies junk.

## Cell map

| row | col | gold | template_id | title | stand (x y z) | reserved | non_air | paste |
| ---:| ---:| :---:| --- | --- | --- | --- | ---:| --- |
| 0 | 0 | ★ | `bakery_small` | Bakery | `20056 120 20002` | 112×152 | 46348 | unverified |
| 0 | 1 | ★ | `barn_red_large` | Barn with Silo | `20140 120 20002` | 56×80 | 7488 | ok |
| 0 | 2 | ★ | `beach_hut` | Beach hut | `20178 120 20002` | 20×25 | 323 | ok |
| 0 | 3 | ★ | `berry_farm_small` | Berry farm | `20198 120 20002` | 20×29 | 201 | ok |
| 0 | 4 | ★ | `blacksmith_shop` | Blacksmith | `20254 120 20002` | 92×134 | 42496 | unverified |
| 0 | 5 | ★ | `borgital_strike_cube` | Borgital | `20310 120 20002` | 20×27 | 583 | ok |
| 0 | 6 | ★ | `bridge_oak_short` | Short oak bridge | `20336 120 20002` | 32×22 | 224 | ok |
| 1 | 0 | ★ | `cabin_log` | Log cabin | `20048 120 20154` | 96×140 | 39659 | unverified |
| 1 | 1 | ★ | `carrot_farm_small` | Carrot farm | `20106 120 20154` | 20×29 | 201 | ok |
| 1 | 2 | ★ | `castle_small_keep` | Little castle | `20172 120 20154` | 112×164 | 71494 | unverified |
| 1 | 3 | ★ | `cottage_medium` | Medium cottage | `20280 120 20154` | 104×152 | 46010 | unverified |
| 1 | 4 | ★ | `cow_barn_medium` | Cow barn | `20342 120 20154` | 20×29 | 290 | ok |
| 1 | 5 | ★ | `dock_small` | Dock | `20363 120 20154` | 22×26 | 299 | ok |
| 2 | 0 | ★ | `fishing_hut` | Fishing hut | `20060 120 20318` | 120×176 | 44966 | unverified |
| 2 | 1 | ★ | `giant_flower_house` | Ultimate Giant Flower House | `20188 120 20318` | 136×200 | 74715 | ok |
| 2 | 2 | ★ | `goat_pen_small` | Goat pen | `20266 120 20318` | 20×27 | 145 | ok |
| 3 | 0 | ★ | `gothic_cathedral` | Gothic Cathedral | `20077 120 20518` | 155×135 | 96351 | ok |
| 3 | 1 | ★ | `herb_garden` | Herb garden | `20165 120 20518` | 20×26 | 100 | ok |
| 3 | 2 | ★ | `horse_stable_small` | Horse stable | `20185 120 20518` | 21×29 | 255 | ok |
| 3 | 3 | ★ | `house_cottage_small` | Small cottage | `20252 120 20518` | 112×152 | 27804 | unverified |
| 3 | 4 | ★ | `large_spruce_house` | Large spruce house | `20353 120 20518` | 91×168 | 36496 | ok |
| 4 | 0 | ★ | `library_small` | Library | `20060 120 20686` | 120×176 | 53521 | unverified |
| 4 | 1 | ★ | `lighthouse_short` | Ultimate Lighthouse Keeper Survival Base | `20180 120 20686` | 120×176 | 68833 | unverified |
| 4 | 2 | ★ | `melon_farm_small` | Melon farm | `20250 120 20686` | 20×29 | 201 | ok |
| 4 | 3 | ★ | `mossy_hobbit_hole` | Mossy Hobbit Hole | `20320 120 20686` | 120×152 | 60787 | unverified |
| 4 | 4 | ★ | `potato_farm_small` | Potato farm | `20390 120 20686` | 20×29 | 201 | ok |
| 5 | 0 | ★ | `pumpkin_farm_small` | Pumpkin farm | `20010 120 20862` | 20×29 | 201 | ok |
| 5 | 1 | ★ | `rabbit_hutch_small` | Rabbit hutch | `20030 120 20862` | 20×25 | 202 | ok |
| 5 | 2 | ★ | `tavern_small` | Tavern | `20092 120 20862` | 104×140 | 32161 | unverified |
| 5 | 3 | ★ | `treehouse_oak` | Oak treehouse | `20196 120 20862` | 104×152 | 47548 | ok |
| 100 | 4 | ★ | `watchtower_tall` | Watchtower | `20101 120 21222` | 24×34 | 476 | ok |
| 5 | 5 | ★ | `wheat_farm_small` | Wheat farm | `20370 120 20862` | 20×29 | 201 | ok |
| 100 | 0 | ★ | `windmill_small` | Windmill | `20012 120 21222` | 24×56 | 917 | ok |
| 6 | 1 | ★ | `wizard_tower` | Wizard tower | `20164 120 21026` | 104×152 | 24577 | unverified |
| 100 | 5 | ★ | `workshop_small` | Workshop | `20133 120 21222` | 40×34 | 214 | ok |
| 6 | 3 | ★ | `zen_garden` | Zen garden | `20362 120 21026` | 20×29 | 132 | ok |
| 100 | 1 | ★ | `sheep_pen_medium` | Sheep pen | `20034 120 21222` | 21×31 | 280 | ok |
| 100 | 2 | ★ | `garden_plot` | Garden plot | `20055 120 21222` | 20×29 | 166 | ok |
| 100 | 3 | ★ | `tree_oak_large` | Large oak tree | `20077 120 21222` | 24×34 | 130 | ok |
