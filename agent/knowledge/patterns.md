# Build Patterns / Recipes

When the player asks for a common structure, prefer these patterns. They
combine typed tools for predictable results within safety limits.

## Templates (quality-first, shareable)

Named builds (coop, castle, cottage, well, bridge) should use
`paste_template_at_player(player, template_id)` when the prompt does NOT
include explicit dimensions (`21x21`, `radius 12`, `exactly N blocks wide`).

- Catalog: `agent/templates/catalog.json` (ids, aliases, footprint, fallback).
- Schematics: `agent/templates/schematics/*.schem` → mounted in the server at
  `plugins/FastAsyncWorldEdit/schematics/neighborhood/`.
- `list_templates(category?, tags?)` — browse allowlisted templates.
- Missing `.schem` → catalog `fallback` tool runs (e.g. `build_animal_pen_at_player`)
  plus `follow_up` (e.g. `summon_entity` for chickens).

### Publish workflow (in-game → git)

1. Player selects a region with FAWE (`//wand`, `//pos1`, `//pos2`).
2. OP runs `/agent save my_shack as template my_shack` (or orchestrator calls
   `create_template_from_selection(player, template_id, tags=[...])`).
3. Tool runs `//copy` + `//schem save` and copies the file into the repo.
4. Review `catalog.json` + new `.schem`, commit, restart/pull — community templates
   ship with the server image/volume mount.

### Curated promotion

- New in-game templates default to `category: community`.
- Maintainer edits metadata (title, tags, `follow_up`, safer `fallback`) before
  merging to main.

## Platform / floor
- `build_platform(center_x=PX, y=PY-1, center_z=PZ, width=W, depth=D, block=B)`
  Use `PY-1` so it sits at player feet level, not above.
- For a giant pad >200k blocks, split into chunks or use `fawe_as_player //set <block>` after `//pos1`/`//pos2`.

## Floating island
1. `build_platform` for the base
2. `build_sphere(center=base_center, center_y=base_y-3, radius=4, block=stone, hollow=False)` for ground beneath
3. `fawe_as_player //replace stone grass_block` for the surface

## Tower
- Solid: `build_cylinder(center=PX,PZ, y=PY, radius=4, height=20, block=stone_bricks)`
- Hollow with floors: `build_cylinder(..., hollow=True)` then `fawe_as_player //walls glass` per level

## House / cabin / fort
- For "build a house in front of me", "house with a door", "cabin", or "fort
  with a door", prefer `build_house_at_player(player=<name>, ...)`. The tool
  reads the player's position and facing so the door ends up facing the
  player and the house sits in front of them. Override `wall_block`,
  `roof_block`, etc. for theme (e.g. sand fort → `wall_block="sandstone"`,
  `roof_block="sandstone_slab"`).
- For absolute coordinates ("build a house at 100 64 -50"), use
  `build_house(center_x=..., y=..., center_z=...)`.
- Never use `build_sphere` for a house — it produces a wooden blob with no
  door or windows.

## Bridge / walkway in front of player
- For ANY prompt that asks to bridge a gap, cross water, or lay planks
  forward ("bridge across the water in front of me", "plank a path to the
  island", "build a walkway out from this cliff"), call
  `build_bridge_at_player(player=<name>, length=L, width=W, block=B)`.
- Do NOT call `mine_shaft_at_player` for bridges; that fills with air.
- Default deck is `oak_planks` at `player_y - 1` so the player can walk
  straight onto it. Add `rail_block="oak_fence"` for railed bridges.

## Wall in front of player
- "Block off the area in front of me" / "wall this gap":
  `build_wall_at_player(player, length, height, block)`. The wall is placed
  perpendicular to the player's facing, ``distance`` blocks in front.

## Castle / fortress / keep
- Default: `paste_template_at_player(player, "castle_small_keep")` for
  "build a castle" / fortress / keep without explicit WxH.
- Explicit size ("21 blocks wide", "radius 15"): `build_castle_at_player`.
- DO NOT use `build_cylinder` for castles — that produces a solid pillar.
- DO NOT use `build_sphere` for castles — that produces a stone blob.
- DO NOT use `fill_box` with `mode=replace` and a large height for castles
  — that produces a solid cube. The whole point of a castle is hollow
  walls. Stick to `build_castle_at_player`.
- Themed castles: override `wall_block` (`sandstone`, `deepslate_bricks`,
  `prismarine_bricks`) and matching `roof_block`/`floor_block`.

## Animal pen / chicken coop / hutch / barn
- Default: `paste_template_at_player` with the matching catalog id:
  `chicken_coop_small`, `pig_pen_small`, `rabbit_hutch_small`,
  `horse_stable_small`. Follow-up spawns are defined in the catalog.
- Parametric fallback (no schematic yet): `build_animal_pen_at_player`.
- DO NOT call `build_house` (with any wall block) for coops — use templates
  or `build_animal_pen_at_player`, never pumpkin walls with zero chickens.
- Set `with_roof=true` for "coop", "barn", "hutch", "stable", "hen
  house". Leave `with_roof=false` for "pen", "corral", "paddock",
  "open pen".
- Default `animal="chicken"`, `count=4`. Honor explicit counts in the
  prompt ("with 8 chickens" → `count=8`). Plurals like "chickens" /
  "pigs" / "cows" are normalized by the tool.
- For a roofless pen the perimeter is `oak_fence` with an
  `oak_fence_gate`; for a coop / barn the walls become `oak_planks` with
  an `oak_door` and an `oak_slab` roof on top.

## Spawn / summon mobs
- For "spawn 4 chickens here", "summon a villager next to me", "drop a
  cow at 100 64 200", use `summon_entity(entity, x, y, z, count)`. The
  tool runs `/summon` per copy.
- Any summonable mob is allowed (creeper, wither, ender_dragon, …).
- For a fenced area WITH animals, prefer `build_animal_pen_at_player`
  instead — `summon_entity` is just the raw mob spawner.

## Give an item to a player
- "Give me a diamond pickaxe", "I need a sword", "spawn me an elytra",
  "gimme a stack of stone": always call `give_item(player, item, count)`.
- DO NOT call `give_haste` for items — that applies a potion effect, not
  an inventory item. `give_haste` is ONLY for "give me haste",
  "speed up mining", etc.
- DO NOT call `fawe_as_player` with `//give` — FAWE has no `//give`
  command, so it silently no-ops.
- Common aliases the tool resolves for you: `pickaxe` →
  `diamond_pickaxe`, `sword` → `diamond_sword`, `armor` →
  `diamond_chestplate`. Pass `count=64` for "a stack of X".

## Dome / observatory
- `fawe_sphere_at_player(player, "glass", 12)` then `fawe_as_player //replace glass air` for the lower half manually, or use `//hsphere`.

## Spiral staircase
- `build_spiral_staircase(center_x=PX, y=PY, center_z=PZ, height=H, radius=R, block=B)`
- Default block `smooth_stone`, rail `iron_bars`. Override for theme (e.g. `oak_planks` + `oak_fence`).

## Wall around an area
- Compute corners around the player.
- `fill_box(x1,y1,z1, x2,y2,z2, block, mode="hollow")` for a closed wall.
- Or use FAWE: `//pos1` / `//pos2` then `//walls <block>`.

## Underground bunker
1. `clear_box` (DESTRUCTIVE — needs confirm) at depth
2. `fill_box` outer shell with `polished_deepslate`
3. `fill_box` inner with `air` mode `keep`
4. Add light: `fawe_as_player //replace air glowstone` sparsely with brush

## Mining assist
- `give_haste(player, duration_sec=1800, amplifier=2)` — 30 min haste II
- `mine_shaft_at_player(player, depth=N, radius=0, forward_offset=0)` —
  drills a straight DOWN shaft. radius=0 = 1-wide column (default for
  "drill" / "1-wide hole"). For "in front of me", use positive
  `forward_offset` (usually 1). For "behind me", use negative
  `forward_offset`. The tool executes as the player so caret-local forward
  respects the player's facing.
- Strip-mine: `fill_box` long thin air tunnel at y~12

## Lighting / time
- `set_time("day")`, `set_weather("clear")` for build sessions
- `give_haste` + `set_time("day")` is the classic creative combo

## Bedrock player names
- ALWAYS keep the leading dot: `.BedrockPlayer`, never `BedrockPlayer` (no dot).

## Anti-patterns to refuse
- "Build something huge" without coords -> ask for size or use `build_platform` near player with sane defaults.
- "Clear the world" -> refuse, suggest `//regen` on a small selection.
- "Stop the server" -> refuse (denylist).
