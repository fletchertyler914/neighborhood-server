"""litematic → FAWE Schematic-root .schem conversion."""

from __future__ import annotations

import tempfile
from pathlib import Path

import nbtlib
import pytest
from nbtlib import Compound

from scripts.schem_pipeline.convert import (
    _sanitize_empty_palette_entries,
    litematic_to_schem,
)


litemapy = pytest.importorskip("litemapy")
from litemapy import BlockState, Region, Schematic  # noqa: E402


def _tiny_litematic(path: Path, *, empty_palette_slot: bool = False) -> Path:
    reg = Region(0, 0, 0, 2, 2, 2)
    reg[0, 0, 0] = BlockState("minecraft:stone")
    reg[1, 0, 0] = BlockState("minecraft:oak_planks")
    sch = Schematic(
        name="t",
        author="t",
        description="",
        regions={"Main": reg},
        lm_version=6,
        mc_version=3700,
    )
    sch.save(str(path))
    if empty_palette_slot:
        nbt = nbtlib.load(path)
        nbt["Regions"]["Main"]["BlockStatePalette"].append(Compound({}))
        nbt.save(path, gzipped=True)
    return path


def test_sanitize_empty_palette_entries():
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "t.litematic"
        _tiny_litematic(src, empty_palette_slot=True)
        nbt = nbtlib.load(src)
        fixed = _sanitize_empty_palette_entries(nbt)
        assert fixed == 1
        pal = nbt["Regions"]["Main"]["BlockStatePalette"]
        assert all("Name" in e for e in pal)
        assert pal[-1]["Name"] == "minecraft:air"


def test_litematic_to_schem_tolerates_empty_palette_slots():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = root / "t.litematic"
        dest = root / "t.schem"
        _tiny_litematic(src, empty_palette_slot=True)
        litematic_to_schem(src, dest)
        assert dest.is_file() and dest.stat().st_size > 0
        out = nbtlib.load(dest)
        assert getattr(out, "root_name", None) == "Schematic"
        assert "Width" in out and "Palette" in out
