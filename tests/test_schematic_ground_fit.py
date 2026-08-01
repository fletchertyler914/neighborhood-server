"""Regression: curated schematics must not float above their foundation.

Seed capture historically left a full stone pad at y=0, an empty y=1, and the
building at y=2+. That pastes as an unnatural air gap. Guard the corpus with
the same check as ``scripts/fix_schematic_ground_gaps.py --check``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fix_schematic_ground_gaps.py"
SCHEM_DIR = ROOT / "agent" / "templates" / "schematics"


def _load_fixer():
    spec = importlib.util.spec_from_file_location("fix_schematic_ground_gaps", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def fixer():
    return _load_fixer()


def test_catalog_schematics_have_no_internal_y_gaps(fixer):
    paths = sorted(SCHEM_DIR.glob("*.schem"))
    assert paths, f"expected schematics in {SCHEM_DIR}"
    bad = []
    for path in paths:
        info = fixer.analyze_file(path)
        if info["internal_gaps"]:
            bad.append(f"{info['file']}: gaps={info['internal_gaps']}")
    assert not bad, "internal foundation/wall air gaps:\n" + "\n".join(bad)


def test_castle_small_keep_stairs_reach_foundation(fixer):
    path = SCHEM_DIR / "castle_small_keep.schem"
    assert path.is_file()
    schem = fixer.load_schem(path)
    solid = fixer.solid_per_y(schem)
    assert fixer.internal_gaps(solid) == []
    stairs = fixer._stair_cells(schem)
    assert stairs, "castle should have entrance stairs"
    min_y = min(y for _, y, _, _ in stairs)
    assert min_y == 1, f"bottom stair should sit on foundation (y=1), got y={min_y}"
