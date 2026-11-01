# Shulkr curated mega builds

Kid hand-picked Shulkr schematics dropped into `agent/templates/schematics/`.
Native paste bbox cap is **2,000,000** (`max-paste-volume` in plugin `config.yml`;
Python `MINECRAFT_MCP_MAX_BLOCKS` default matches).

| File | Catalog id | Author | Non-air | Bbox | Pasteable |
| --- | --- | --- | --- | --- | --- |
| `gothic_cathedral.schem` | `gothic_cathedral` | Kiga | ~155,472 | 147×133×85 = 1,661,835 | yes (under 2M) |
| `large_spruce_house.schem` | `large_spruce_house` | ben | ~54,493 | 83×43×107 = 381,883 | yes |
| `borgital_strike_cube.schem` | `borgital_strike_cube` | Kajofajo/baonam | ~583 | 9×15×9 = 1,215 | yes |
| `mossy_hobbit_hole.schem` | `mossy_hobbit_hole` | BuildSchem (SchemCraft) | ~82,820 | 112×64×96 = 688,128 | yes (under 2M) |
| `giant_flower_house.schem` | `giant_flower_house` | BuildSchem (SchemCraft) | ~153,897 | 128×88×128 = 1,441,792 | yes (under 2M) |

Provenance URLs live on each catalog entry (`source_url`). Shulkr rows are
marked `All-Rights-Reserved` pending upstream SPDX; SchemCraft BuildSchem
rows (`mossy_hobbit_hole`, `giant_flower_house`) are `CC-BY-4.0`.
Friends-server curated use.

After adding more gold assets, optionally re-run `make qa-grid` to place them on
the remote QA campus (does not wipe the world pad layout docs until regenerated).
