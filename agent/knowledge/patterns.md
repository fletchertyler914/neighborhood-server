# Build Patterns / Recipes

When the player asks for a common structure, prefer these patterns. They
combine typed tools for predictable results within safety limits.

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
- `mine_shaft_at_player(player, depth=64)` — vertical 2-wide shaft
- Strip-mine: `fill_box` long thin air tunnel at y~12

## Lighting / time
- `set_time("day")`, `set_weather("clear")` for build sessions
- `give_haste` + `set_time("day")` is the classic creative combo

## Bedrock player names
- ALWAYS keep the leading dot: `.LunarLicense582`, never `LunarLicense582`.

## Anti-patterns to refuse
- "Build something huge" without coords -> ask for size or use `build_platform` near player with sane defaults.
- "Clear the world" -> refuse, suggest `//regen` on a small selection.
- "Stop the server" -> refuse (denylist).
