"""Coverage matrix validation for eval suites."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agent.eval.case import EvalCase, CaseMode


def load_coverage(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"coverage file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "intent_families" not in data:
        raise ValueError(f"{path}: expected top-level intent_families")
    return data


def required_case_ids(coverage: dict[str, Any]) -> set[str]:
    """Collect every case id listed in the coverage matrix."""

    out: set[str] = set()
    families = coverage.get("intent_families") or {}
    for _family, modes in families.items():
        if not isinstance(modes, dict):
            continue
        for _mode, severities in modes.items():
            if not isinstance(severities, dict):
                continue
            for _sev, ids in severities.items():
                if isinstance(ids, list):
                    out.update(str(i) for i in ids)
    return out


def validate_coverage(
    cases: list[EvalCase],
    coverage_path: Path,
) -> list[str]:
    """Return human-readable errors if coverage requirements are unmet."""

    errors: list[str] = []
    coverage = load_coverage(coverage_path)
    required = required_case_ids(coverage)
    present = {c.id for c in cases}

    missing = sorted(required - present)
    if missing:
        errors.append(f"coverage requires missing case ids: {', '.join(missing)}")

    extra = sorted(present - required)
    if extra:
        errors.append(
            f"coverage lists no requirement for case ids: {', '.join(extra)}"
        )

    # Each required case must support the mode implied by coverage path
    families = coverage.get("intent_families") or {}
    for family, modes in families.items():
        if not isinstance(modes, dict):
            continue
        for mode_name, severities in modes.items():
            if not isinstance(severities, dict):
                continue
            try:
                mode_enum = CaseMode(mode_name)
            except ValueError:
                errors.append(f"unknown mode in coverage: {mode_name}")
                continue
            for sev, ids in severities.items():
                if not isinstance(ids, list):
                    continue
                for case_id in ids:
                    match = next((c for c in cases if c.id == case_id), None)
                    if match is None:
                        continue
                    if mode_enum not in match.modes:
                        errors.append(
                            f"{case_id}: coverage expects mode {mode_name} "
                            f"but case modes={[m.value for m in match.modes]}"
                        )
                    if match.severity.value != sev:
                        errors.append(
                            f"{case_id}: coverage lists severity {sev} "
                            f"but case has {match.severity.value}"
                        )

    return errors
