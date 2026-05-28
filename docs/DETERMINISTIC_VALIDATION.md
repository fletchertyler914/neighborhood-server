# Deterministic validation gates

The builder stack enforces **schema → tool → command → world** with drift detection at each layer.

## MCP Core v1 (`agent/mcp_core.py`)

- Capability tiers: `CORE_REQUIRED`, builders, FAWE selection/transform/motion/shaping/generation/history
- `MCP_CORE_VERSION` and `TOOLS_VERSION` exposed via `server_capabilities()`

## Executor boundary (`agent/executor.py`)

Every registered tool call:

1. **Normalizes** arguments (schema defaults, strip unknown keys when strict)
2. **Validates** against JSON Schema (`agent/schema_validate.py`)
3. **Dispatches** via `_execute_tool_raw` (no recursive re-entry)
4. **Attaches** `deterministic_signature` (SHA-256 of tool + args + commands + versions)
5. **Attaches** `execution_metadata` (`policy_path`, `safety_level`, `server_capability_version`)

Escape hatches (`run_command`, `fawe_as_player`) use `policy_path: escape_hatch`.

## Catalog validation (`agent/templates/catalog.py`)

At load time:

- Template ids and fallback tool names must exist in `TOOL_DEFINITIONS`
- `fallback_steps` support `${ax}`, `${ay+N}`, `${az}` anchor expressions (`agent/templates/anchor.py`)

## CI gates

| Gate | Tests |
|------|--------|
| Tool schemas + registry | `tests/test_schema_tools.py` |
| Executor signatures | `tests/test_executor.py` |
| Template catalog | `tests/test_templates.py`, `tests/test_gold_catalog.py` |
| Pack spec | `tests/test_pack_spec.py` |
| FAWE primitives | `tests/test_fawe_tools.py` |
| Orchestrator rewrites | `tests/test_orchestrator_contract.py` |
| Eval fixtures | `tests/test_eval_fixture_gate.py` |

Run:

```bash
python3 -m pytest tests/ -q --ignore=tests/integration
```

## World verification (seed pipeline)

`agent/templates/seed.py` + `scripts/seed-templates.sh` build fallbacks in an isolated sandbox (`AGENT_SEED_SANDBOX_*` coords) and verify schematic availability. Live-server seeding requires `AGENT_SEED_PLAYER`.

## Routing audit

Each orchestrator job records `routing` on the audit entry:

- `intent_family`, `selected_tool`, `selected_template_id`
- `fallback_reason`, `rewrite_applied`, `original_tool`
- `source_id`, `content_hash` (template provenance)

These fields flow into feedback and SFT/DPO exports (`agent/training/feedback.py`).
