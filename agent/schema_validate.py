"""Minimal JSON-schema validation for MCP tool arguments (no external deps)."""

from __future__ import annotations

from typing import Any


class SchemaValidationError(ValueError):
    pass


def validate_against_schema(
    value: Any,
    schema: dict[str, Any],
    *,
    path: str = "$",
) -> None:
    """Validate *value* against a restricted JSON Schema subset."""

    stype = schema.get("type")
    if isinstance(stype, list):
        if not any(_matches_type(value, t) for t in stype):
            raise SchemaValidationError(f"{path}: type mismatch")
        if value is None and "null" in stype:
            return
        stype = next(t for t in stype if _matches_type(value, t))
    elif stype and not _matches_type(value, stype):
        raise SchemaValidationError(f"{path}: expected {stype}, got {type(value).__name__}")

    if stype == "object":
        if not isinstance(value, dict):
            raise SchemaValidationError(f"{path}: expected object")
        props = schema.get("properties") or {}
        required = schema.get("required") or []
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(props)
            if extra:
                raise SchemaValidationError(f"{path}: unknown properties: {sorted(extra)}")
        for key in required:
            if key not in value:
                raise SchemaValidationError(f"{path}: missing required field {key!r}")
        for key, sub in props.items():
            if key in value:
                validate_against_schema(value[key], sub, path=f"{path}.{key}")
        return

    if stype == "array":
        if not isinstance(value, list):
            raise SchemaValidationError(f"{path}: expected array")
        items = schema.get("items")
        if items:
            for i, item in enumerate(value):
                validate_against_schema(item, items, path=f"{path}[{i}]")
        return

    if stype == "string":
        if not isinstance(value, str):
            raise SchemaValidationError(f"{path}: expected string")
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise SchemaValidationError(f"{path}: string too short")
        if "enum" in schema and value not in schema["enum"]:
            raise SchemaValidationError(f"{path}: must be one of {schema['enum']}")
        return

    if stype == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise SchemaValidationError(f"{path}: expected integer")
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaValidationError(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaValidationError(f"{path}: above maximum {schema['maximum']}")
        return

    if stype == "boolean":
        if not isinstance(value, bool):
            raise SchemaValidationError(f"{path}: expected boolean")
        return


def _matches_type(value: Any, stype: str) -> bool:
    if stype == "null":
        return value is None
    if stype == "string":
        return isinstance(value, str)
    if stype == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if stype == "boolean":
        return isinstance(value, bool)
    if stype == "array":
        return isinstance(value, list)
    if stype == "object":
        return isinstance(value, dict)
    return True
