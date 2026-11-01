#!/usr/bin/env python3
"""Regenerate garden/farm plant schematics with dirt, farmland, and plants.

The original seed fallbacks used stone_bricks/moss platforms, so
``garden_plot.schem`` pasted as a stone grid. This writer emits Sponge
schematic v3 files compatible with FAWE 2.15.
"""

from __future__ import annotations

import gzip
import time
from pathlib import Path

from nbtlib import Byte, ByteArray, Compound, File, Int, IntArray, Long, Short, String

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "agent" / "templates" / "schematics"
DATA_VERSION = 4790


def _varint_bytes(values: list[int]) -> bytes:
    out = bytearray()
    for value in values:
        value = int(value)
        while True:
            bits = value & 0x7F
            value >>= 7
            if value:
                out.append(bits | 0x80)
            else:
                out.append(bits)
                break
    return bytes(out)


def write_schem(
    path: Path,
    *,
    width: int,
    height: int,
    length: int,
    blocks: list[str],
) -> None:
    if len(blocks) != width * height * length:
        raise ValueError(f"{path.name}: expected {width*height*length} blocks, got {len(blocks)}")
    palette: dict[str, int] = {}
    indices: list[int] = []
    for name in blocks:
        if name not in palette:
            palette[name] = len(palette)
        indices.append(palette[name])
    palette_tag = Compound({name: Int(idx) for name, idx in palette.items()})
    root = Compound(
        {
            "Schematic": Compound(
                {
                    "Version": Int(3),
                    "DataVersion": Int(DATA_VERSION),
                    "Metadata": Compound({"Date": Long(int(time.time() * 1000))}),
                    "Width": Short(width),
                    "Height": Short(height),
                    "Length": Short(length),
                    "Offset": IntArray([Int(-(width // 2)), Int(0), Int(-(length // 2))]),
                    "Blocks": Compound(
                        {
                            "Palette": palette_tag,
                            "Data": ByteArray(list(_varint_bytes(indices))),
                        }
                    ),
                }
            )
        }
    )
    # FAWE reads gzip-compressed schem; nbtlib File gzip=True matches seed output.
    File(root).save(str(path), gzipped=True)
    print(f"wrote {path.relative_to(ROOT)} ({width}x{height}x{length}, {len(palette)} palette)")


def _idx(x: int, y: int, z: int, w: int, h: int, l: int) -> int:
    return (y * l + z) * w + x


def _empty(w: int, h: int, l: int) -> list[str]:
    return ["minecraft:air"] * (w * h * l)


def garden_plot() -> None:
    """9×3×9 flower/veggie garden: dirt beds, oak border, flowers + crops."""
    w, h, l = 9, 3, 9
    b = _empty(w, h, l)
    flowers = [
        "minecraft:poppy",
        "minecraft:dandelion",
        "minecraft:azure_bluet",
        "minecraft:oxeye_daisy",
        "minecraft:cornflower",
        "minecraft:allium",
    ]
    for x in range(w):
        for z in range(l):
            edge = x in (0, w - 1) or z in (0, l - 1)
            b[_idx(x, 0, z, w, h, l)] = (
                "minecraft:oak_log[axis=y]" if edge else "minecraft:dirt"
            )
            if edge:
                continue
            # Center path of coarse dirt; planted beds elsewhere.
            if x == w // 2 or z == l // 2:
                b[_idx(x, 0, z, w, h, l)] = "minecraft:coarse_dirt"
                continue
            if (x + z) % 3 == 0:
                b[_idx(x, 0, z, w, h, l)] = "minecraft:farmland[moisture=7]"
                b[_idx(x, 1, z, w, h, l)] = "minecraft:wheat[age=7]"
            else:
                b[_idx(x, 0, z, w, h, l)] = "minecraft:grass_block"
                b[_idx(x, 1, z, w, h, l)] = flowers[(x * 3 + z) % len(flowers)]
    # Little water trough for farmland.
    b[_idx(4, 0, 2, w, h, l)] = "minecraft:water[level=0]"
    b[_idx(4, 0, 6, w, h, l)] = "minecraft:water[level=0]"
    write_schem(OUT / "garden_plot.schem", width=w, height=h, length=l, blocks=b)


def herb_garden() -> None:
    w, h, l = 8, 3, 8
    b = _empty(w, h, l)
    plants = [
        "minecraft:sweet_berry_bush[age=3]",
        "minecraft:flowering_azalea",
        "minecraft:lilac[half=lower]",
        "minecraft:peony[half=lower]",
        "minecraft:fern",
        "minecraft:red_tulip",
    ]
    for x in range(w):
        for z in range(l):
            edge = x in (0, w - 1) or z in (0, l - 1)
            b[_idx(x, 0, z, w, h, l)] = (
                "minecraft:stripped_oak_log[axis=y]" if edge else "minecraft:podzol"
            )
            if not edge:
                b[_idx(x, 1, z, w, h, l)] = plants[(x + z * 2) % len(plants)]
    write_schem(OUT / "herb_garden.schem", width=w, height=h, length=l, blocks=b)


def zen_garden() -> None:
    w, h, l = 11, 3, 11
    b = _empty(w, h, l)
    for x in range(w):
        for z in range(l):
            edge = x in (0, w - 1) or z in (0, l - 1)
            if edge:
                b[_idx(x, 0, z, w, h, l)] = "minecraft:stone"
            elif abs(x - w // 2) <= 1 or abs(z - l // 2) <= 1:
                b[_idx(x, 0, z, w, h, l)] = "minecraft:gravel"
            else:
                b[_idx(x, 0, z, w, h, l)] = "minecraft:moss_block"
                if (x + z) % 4 == 0:
                    b[_idx(x, 1, z, w, h, l)] = "minecraft:bamboo[age=1,leaves=small,stage=0]"
                elif (x * z) % 5 == 0:
                    b[_idx(x, 1, z, w, h, l)] = "minecraft:azalea"
    # Center stone lantern vibe (lantern needs support — use flower pot).
    b[_idx(5, 1, 5, w, h, l)] = "minecraft:flower_pot"
    write_schem(OUT / "zen_garden.schem", width=w, height=h, length=l, blocks=b)


def _crop_farm(name: str, crop_block: str, size: int = 11) -> None:
    w = h_dim = l = size
    h = 3
    b = _empty(w, h, l)
    for x in range(w):
        for z in range(l):
            edge = x in (0, w - 1) or z in (0, l - 1)
            if edge:
                b[_idx(x, 0, z, w, h, l)] = "minecraft:oak_log[axis=y]"
            elif x == w // 2 and z == l // 2:
                b[_idx(x, 0, z, w, h, l)] = "minecraft:water[level=0]"
            else:
                b[_idx(x, 0, z, w, h, l)] = "minecraft:farmland[moisture=7]"
                b[_idx(x, 1, z, w, h, l)] = crop_block
    write_schem(OUT / f"{name}.schem", width=w, height=h, length=l, blocks=b)


def main() -> None:
    garden_plot()
    herb_garden()
    zen_garden()
    _crop_farm("wheat_farm_small", "minecraft:wheat[age=7]")
    _crop_farm("carrot_farm_small", "minecraft:carrots[age=7]", size=11)
    _crop_farm("potato_farm_small", "minecraft:potatoes[age=7]", size=11)
    _crop_farm("berry_farm_small", "minecraft:sweet_berry_bush[age=3]", size=11)
    _crop_farm("pumpkin_farm_small", "minecraft:pumpkin", size=11)
    _crop_farm("melon_farm_small", "minecraft:melon", size=11)
    _crop_farm("sugarcane_farm_small", "minecraft:sugar_cane", size=11)
    print("done")


if __name__ == "__main__":
    main()
