# Community publishing (CC-BY outbound)

Internal templates we author are published back to the community under **CC-BY-4.0**.

## Publish a pack

```bash
python3 -m agent.templates.publish \
  --pack-id neighborhood_gold \
  --ids chicken_coop_small castle_small_keep watchtower_tall
```

Output: `agent/templates/published/<pack_id>-<version>/`

- `pack.json` — manifest with footprints, tags, `content_hash` per schematic
- `schematics/` — copied `.schem` files when present in repo
- `LICENSE` — CC-BY-4.0 notice
- `published/index.json` — ledger of published packs
- `published/CHANGELOG.md` — append-only release notes

## Authoring workflow

1. Build in-game with FAWE selection → `create_template_from_selection`
2. Or add a catalog row with `fallback` / `fallback_steps` and run seed
3. Enrich metadata (`source_id`, `license`, `attribution`, `complexity`)
4. Pass pack validator + unit tests
5. Publish bundle for redistribution

## Attribution

Generated credits: `agent/templates/ATTRIBUTION.md` (via `python3 -m agent.templates.ingest --attribution`).

Each catalog row should include:

- `attribution` — human-readable credit line
- `author`, `source_url`, `source_ref`
- `content_hash` — SHA-256 of the `.schem` artifact

## Inbound vs outbound

| Direction | License |
|-----------|---------|
| Inbound `/ai ingest` (private server) | CC0, CC-BY, CC-BY-SA, CC-BY-NC, CC-BY-NC-SA, MIT |
| Inbound community packs (redistributable) | CC0, CC-BY, CC-BY-SA, MIT only |
| Outbound neighborhood packs | CC-BY-4.0 |

Do not publish NC/ND/restricted derivatives.
