# Template ingestion policy

Inbound community templates must pass strict license and provenance checks before they enter `agent/templates/catalog.json`.

## Allowed inbound licenses (SPDX)

- `CC0-1.0`
- `CC-BY-4.0`
- `CC-BY-SA-4.0`
- `CC-BY-NC-4.0` / `CC-BY-NC-SA-4.0` (and 3.0 variants)
- `MIT`

**CC-BY-NC is OK** for this private non-commercial neighborhood server when
`source_url`, `author`, `license`, and `attribution` are persisted on the
catalog entry. Prefer CC-BY when bulk-scraping.

**Rejected:** ND, proprietary, or unknown licenses. See
`agent/templates/license_policy.yaml`. Friends Shulkr ARR needs an explicit
`--allow-arr` override.

## Source allowlist

Community sources are declared in `agent/templates/sources.yaml`:

- `source_id`, pinned `version_pin` (tag or commit — never `main` / `latest`)
- Explicit `license` matching the allowlist
- `enabled: false` until manually verified

Run ingestion only from enabled sources.

## Pack format

Template packs use **Template Pack Spec** (`agent/templates/pack_spec.py`):

- `pack.json` manifest (SPDX, attribution, template list)
- `schematics/*.schem` files referenced by the manifest
- SHA-256 `content_hash` computed at ingest time

Validate with:

```bash
python3 -m agent.templates.ingest --pack-dir path/to/pack --source-id my_source
```

Failures land in `agent/templates/quarantine/<source_id>/validation.json`.

## Merge into catalog

```bash
# Internal gold corpus (~50 templates)
python3 -m agent.templates.ingest --apply-gold

# Regenerate credits
python3 -m agent.templates.ingest --attribution
```

## ID normalization

Canonical ids: `^[a-z][a-z0-9_]{0,63}$`. Community ids should be prefixed with `source_id` when imported from packs to avoid collisions.
