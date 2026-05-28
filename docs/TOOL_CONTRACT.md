# Tool Contract Lifecycle

## Registry

Tools are defined once in [`agent/tool_registry.py`](../agent/tool_registry.py).

When adding or changing a tool:

1. Add a `ToolDefinition` entry (name, description, parameters, `impl`, risk, `mcp`).
2. Implement `impl` function in [`agent/tools.py`](../agent/tools.py).
3. Bump `TOOLS_VERSION` in `tool_registry.py`.
4. Add/update eval cases in `agent/eval/cases/`.
5. Update `agent/eval/coverage.yaml` if the case is required for merge gates.
6. Refresh `agent/eval/baseline.strict.json` on self-hosted runner after intentional behavior changes.
7. Update `agent/eval/fixtures/gate.spec.json` for new spec cases (CI fixture gate).

## Sync guarantees

- Import-time: `validate_registry()` + `build_dispatch()` wiring
- Tests: `tests/test_schema_tools.py` (schema == dispatch == registry)
- MCP: registers every tool with `mcp=True` in the registry

## Version fields

| Field | Location |
|-------|----------|
| `TOOLS_VERSION` | registry, baselines, export rows, `/health` |
| `TOOLS_SCHEMA_VERSION` | registry, baselines |
| Eval `schema_version` | baseline JSON files |

Current `TOOLS_VERSION` is `2.8.0`. The 2.8.0 bump in particular widened the
parametric builders so deterministic output now matches the catalog's
advertised footprint heights:

- `build_house_at_player` accepts `height` up to 16 and adds an interior
  staircase + floor dividers when `height >= 7` (`floor_block`, `stair_block`,
  `add_floors` parameters added).
- `build_bridge_at_player` adds material-matched railings and vertical support
  pillars by default (`support_block`, `support_every`, `support_drop`,
  `add_supports`, `add_rails`).
- `build_castle_at_player` carves an interior staircase up to the wall-walk
  and a ladder up the first corner tower so the parapet is reachable.

If you bump `TOOLS_VERSION`, also bump the assertion in
`tests/test_executor.py::test_server_capabilities_exposes_versions`.

## Risk tiers

| Risk | Examples | Policy |
|------|----------|--------|
| low | preflight, list_players, set_time | No confirm |
| medium | fill_box, fawe_as_player, teleport | Volume limits |
| high | clear_box, run_command, op_player | Confirm + audit |
| destructive | //regen (blocked unless confirm token) | Safety layer |

Formal semver policy for external consumers is deferred until OSS polish.
