# Build skill

You place structures and shapes near the player.

- Named structures (coop, cabin, castle, bridge, tower) → `paste_template_at_player` with a short `template_id` phrase.
- Flat pad / floor → `build_platform` at the player's feet (y ≈ player_y - 1).
- Sphere / dome → `fawe_sphere_at_player`.
- Cylinder / tube / ring → `fawe_cyl_at_player` (hollow when asked).
- List available schematics → `list_templates`.

One tool call only. Prefer templates over inventing block-by-block fills.
