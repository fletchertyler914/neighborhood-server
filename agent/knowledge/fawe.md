# FastAsyncWorldEdit (FAWE) Cheatsheet

Run via `fawe_as_player(player, command)` so the command uses the player's
location and selection. Always include leading `//` for FAWE commands.

## Selection
- `//pos1` / `//pos2` — set selection corners at player feet
- `//hpos1` / `//hpos2` — set at block player is looking at
- `//expand <amount> [direction]` — grow selection
- `//contract <amount> [direction]`
- `//size` — show selection size
- `//count <block>` — count blocks in selection

## Set / replace
- `//set <block>` — fill selection with block
- `//replace <from> <to>` — replace all `from` blocks with `to`
- `//replace <from1>,<from2> <to>` — replace multiple
- `//walls <block>` — only the outer walls
- `//faces <block>` — outer faces (walls + floor + ceiling)
- `//hollow <thickness> <block>` — hollow out
- `//overlay <block>` — single layer on top of solids

## Shapes (centered on player)
- `//sphere <block> <radius>` — solid sphere
- `//hsphere <block> <radius>` — hollow sphere
- `//cyl <block> <radius> [height]` — vertical cylinder
- `//hcyl <block> <radius> [height]` — hollow cylinder
- `//pyramid <block> <size>` — solid pyramid
- `//hpyramid <block> <size>` — hollow pyramid
- `//forestgen <size> <type> <density>` — generate trees

## Movement / copy
- `//copy` — copy selection (player position is anchor)
- `//cut`
- `//paste` — paste at player position
- `//move <amount> [direction]`
- `//stack <count> [direction]`
- `//rotate <yaw> [pitch] [roll]`
- `//flip [direction]`

## Brushes (powerful — use sparingly)
- `//brush sphere <block> <radius>` — paints with right-click
- `//brush cyl <block> <radius>`
- `/none` — clear brush

## Generation
- `//generate <block> <expression>` — math-based shapes
- `//gen` examples:
  - `//gen stone (x^2+y^2+z^2)<400` — sphere of stone
- `//cyl glass 5 10` — quick column

## History
- `//undo [count]` — undo last operations
- `//redo [count]`
- `//clearhistory`

## Schematics
- `//schem save <name>`
- `//schem load <name>`
- `//paste -a` — ignore air

## Destructive flags (require confirm_token)
- `//regen` — regenerate chunks (DESTROYS player builds in selection)
- `//set air` — clears selection
- Large `//replace` with millions of blocks

## Common patterns
- Castle wall: select cuboid -> `//walls stone_bricks`
- Hollow dome: `//hsphere quartz_block 15`
- Glass dome: `//hsphere glass 12`
- Roof tiles: `//replace stone_slab oak_planks` over a `//set` shell
- Tree farm: select grass area -> `//forestgen 10 normal 0.5`
