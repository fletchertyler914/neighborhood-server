# World editing cheat sheet

Prefer **typed MCP tools** over raw `fawe_as_player` / `run_command`.

## Inspection

| Tool | Use |
|------|-----|
| `server_status` | Container + players |
| `preflight` | Pre-flight health |
| `list_players` | Who is online |
| `get_player_position` | XYZ |
| `get_player_dimension` | Overworld/Nether/End |

## Vanilla volumes

| Tool | Use |
|------|-----|
| `fill_box` | Rectangles (`replace`, `hollow`, `outline`, `keep`) |
| `clear_box` | Air fill |
| `build_platform` | Flat deck |
| `build_sphere` / `build_cylinder` | Primitives |
| `build_spiral_staircase` | Stairs |

## Player-relative builders

| Tool | Use |
|------|-----|
| `build_house_at_player` | House with door/windows |
| `build_castle_at_player` | Hollow keep + towers |
| `build_animal_pen_at_player` | Fenced pen + summons |
| `build_bridge_at_player` | Bridge along facing |
| `build_wall_at_player` | Wall segment |
| `mine_shaft_at_player` | Vertical shaft |

## Templates

| Tool | Use |
|------|-----|
| `list_templates` | Catalog browse |
| `paste_template_at_player` | Schematic paste (fallback if no `.schem`) |
| `create_template_from_selection` | Save selection to catalog |

See `agent/templates/catalog.json` for the current template count (101 verified schematics as of tools 2.8.0). Prompt aliases resolve via the hybrid ranker (`docs/TEMPLATE_RANKING.md`).

## FAWE typed primitives

Selection: `select_box`, `select_around_player`, `expand_selection`, `contract_selection`, `selection_size`

Edit: `set_selection`, `replace_in_selection`, `walls_in_selection`, `faces_in_selection`, `hollow_selection`, `overlay_selection`

Motion: `stack_selection`, `move_selection`, `rotate_selection`, `flip_selection`, `copy_selection`, `cut_selection`, `paste_selection_at_player`

Shaping: `smooth_selection`, `naturalize_selection`

Generate: `generate_forest_at_player`, `generate_pyramid_at_player`

History: `undo`, `redo`

Escape hatch: `fawe_as_player` — only when no typed tool exists.

## Limits

- `fill_box` / shape builders: **200,000** blocks max
- Generated commands: **20,000** max
- Destructive ops: confirm via `/agent confirm` in-game

## Host scripts

```bash
./mc.sh status
./mc.sh cmd "time set day"
./scripts/seed-templates.sh --player Steve --missing-only
python3 -m agent.templates.ingest --apply-gold
```

See also: [TEMPLATES.md](TEMPLATES.md), [DETERMINISTIC_VALIDATION.md](DETERMINISTIC_VALIDATION.md).
