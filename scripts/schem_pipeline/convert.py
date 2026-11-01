"""Convert downloaded builds to FAWE Sponge ``.schem`` (prefer native)."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path


class ConvertError(RuntimeError):
    pass


def sniff_format(path: Path) -> str:
    raw = path.read_bytes()[:16]
    name = path.name.lower()
    if name.endswith(".schem"):
        return "schem"
    if name.endswith(".litematic"):
        return "litematic"
    if name.endswith(".mcstructure"):
        return "mcstructure"
    if name.endswith(".nbt"):
        return "nbt"
    # gzip NBT — could be schem or litematic
    if raw[:2] == b"\x1f\x8b":
        try:
            import nbtlib

            nbt = nbtlib.load(path)
            keys = set(nbt.keys())
            if "Regions" in keys or "Metadata" in keys and "MinecraftDataVersion" in keys:
                return "litematic"
            if "Width" in keys and "Palette" in keys:
                return "schem"
            if "Schematic" in keys:
                return "schem"
        except Exception:
            return "gzip-nbt"
    if raw[:4] == b"PK\x03\x04":
        return "zip"
    return "unknown"


def _encode_varints(indices) -> bytes:
    """Sponge Schematic v2 BlockData: unsigned LEB128 varints."""
    out = bytearray()
    for value in indices:
        v = int(value)
        if v < 0:
            raise ConvertError(f"negative palette index {v}")
        while True:
            b = v & 0x7F
            v >>= 7
            if v:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
    return bytes(out)


def _encode_region_blockdata_varints(blocks, width: int, height: int, length: int):
    """Stream YZX palette indices → signed ``array('b')`` for nbtlib ByteArray.

    Avoids a giant Python ``list[int]`` + per-byte ``Byte()`` tags (OOM on
    multi‑million-block Bloxelizer litematics).
    """
    import array

    out = bytearray()
    for y in range(height):
        for z in range(length):
            for x in range(width):
                v = int(blocks[x, y, z])
                if v < 0:
                    raise ConvertError(f"negative palette index {v}")
                while True:
                    b = v & 0x7F
                    v >>= 7
                    if v:
                        out.append(b | 0x80)
                    else:
                        out.append(b)
                        break
    return array.array("b", (b - 256 if b >= 128 else b for b in out))


def _sanitize_empty_palette_entries(nbt) -> int:
    """Replace empty BlockStatePalette compounds with minecraft:air.

    Bloxelizer (and some exporters) emit ``{}`` palette slots. litemapy requires
    a ``Name`` tag and crashes with KeyError otherwise.
    """
    from nbtlib import Compound, String

    fixed = 0
    regions = nbt.get("Regions") or {}
    for reg in regions.values():
        pal = reg.get("BlockStatePalette")
        if pal is None:
            continue
        for i, entry in enumerate(pal):
            if "Name" not in entry:
                pal[i] = Compound({"Name": String("minecraft:air")})
                fixed += 1
    return fixed


def litematic_to_schem(src: Path, dest: Path, *, data_version: int = 2586) -> Path:
    try:
        from litemapy import Schematic
        from nbtlib import ByteArray, File, Int, IntArray, List, Compound, Short
        import nbtlib
    except ImportError as exc:
        raise ConvertError(
            "litemapy is required for .litematic → .schem conversion.\n"
            "  pip install litemapy\n"
            "Or convert in browser: https://bloxelizer.com/converter"
        ) from exc

    raw = nbtlib.load(src)
    _sanitize_empty_palette_entries(raw)
    try:
        dv = int(raw.get("MinecraftDataVersion") or data_version)
    except Exception:
        dv = data_version
    try:
        schematic = Schematic.from_nbt(raw)
    except Exception as exc:
        raise ConvertError(f"litematic parse failed for {src.name}: {exc}") from exc
    if not schematic.regions:
        raise ConvertError(f"litematic has no regions: {src}")
    # Prefer largest region by volume.
    region = max(
        schematic.regions.values(),
        key=lambda r: abs(int(r.width) * int(r.height) * int(r.length)),
    )

    width = abs(int(region.width))
    height = abs(int(region.height))
    length = abs(int(region.length))
    # Sponge v2 stores dims as Short — refuse absurd sizes early.
    if max(width, height, length) > 32767:
        raise ConvertError(
            f"region {width}x{height}x{length} exceeds Sponge Short dim limit"
        )

    # Always use the stream encoder: litemapy's to_sponge_nbt uses Byte() for
    # palette indices (breaks at >127) and materializes huge tag lists.
    region._optimize_palette()  # noqa: SLF001 — public API has no hook
    palette_blocks = list(region._Region__palette)  # noqa: SLF001
    blocks = region._Region__blocks  # noqa: SLF001

    nbt = File(gzipped=True, byteorder="big")
    nbt["DataVersion"] = Int(dv)
    nbt["Version"] = Int(2)
    nbt["Width"] = Short(width)
    nbt["Height"] = Short(height)
    nbt["Length"] = Short(length)
    nbt["Offset"] = IntArray([Int(0), Int(0), Int(0)])
    nbt["Entities"] = List[Compound]()
    nbt["BlockEntities"] = List[Compound]()
    nbt["PaletteMax"] = Int(len(palette_blocks))
    palette = Compound()
    for i, block in enumerate(palette_blocks):
        palette[block.to_block_state_identifier()] = Int(i)
    nbt["Palette"] = palette
    nbt["BlockData"] = ByteArray(
        _encode_region_blockdata_varints(blocks, width, height, length)
    )

    # FAWE ClipboardFormats.findByFile requires the gzip-NBT root name
    # ``Schematic`` (unnamed roots → "unsupported schematic format").
    _ensure_schematic_root_name(nbt)
    dest.parent.mkdir(parents=True, exist_ok=True)
    nbt.save(dest, gzipped=True)
    return dest


def _ensure_schematic_root_name(nbt) -> None:
    """Set Sponge v2 root name so FAWE recognizes the file."""

    if getattr(nbt, "root_name", None) != "Schematic":
        nbt.root_name = "Schematic"


def normalize_schem_root(path: Path) -> bool:
    """Rewrite ``path`` in place if root name is not ``Schematic``. Returns True if changed."""

    import nbtlib

    nbt = nbtlib.load(path)
    # Nested v3 ``{Schematic:{...}}`` under unnamed root is already FAWE-readable.
    if "Schematic" in nbt and list(nbt.keys()) == ["Schematic"]:
        return False
    if getattr(nbt, "root_name", None) == "Schematic":
        return False
    if "Width" not in nbt or "Palette" not in nbt:
        return False
    nbt.root_name = "Schematic"
    nbt.save(path, gzipped=True)
    return True


def ensure_schem(
    src: Path,
    dest: Path,
    *,
    skip_mcstructure: bool = True,
) -> Path:
    """Materialize a Sponge ``.schem`` at ``dest`` from ``src``."""
    fmt = sniff_format(src)
    if fmt == "mcstructure" and skip_mcstructure:
        raise ConvertError("skipping .mcstructure (disabled in config)")
    if fmt == "schem":
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        normalize_schem_root(dest)
        return dest
    if fmt == "litematic" or (fmt == "gzip-nbt" and src.suffix.lower() != ".schem"):
        # Bloxelizer CDN often serves gzip litematic without extension.
        if fmt == "gzip-nbt":
            # Peek: if not litematic, treat as schem copy.
            try:
                return litematic_to_schem(src, dest)
            except Exception:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                return dest
        return litematic_to_schem(src, dest)
    if fmt == "zip":
        import tempfile
        import zipfile

        with tempfile.TemporaryDirectory(prefix="schem_conv_") as tmp:
            root = Path(tmp)
            with zipfile.ZipFile(src) as zf:
                zf.extractall(root)
            schems = sorted(root.rglob("*.schem"), key=lambda p: -p.stat().st_size)
            if schems:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(schems[0], dest)
                return dest
            lites = sorted(root.rglob("*.litematic"), key=lambda p: -p.stat().st_size)
            if lites:
                return litematic_to_schem(lites[0], dest)
        raise ConvertError(f"zip had no .schem/.litematic: {src}")
    raise ConvertError(f"unsupported format {fmt!r} for {src}")


def gunzip_copy(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(src, "rb") as zin, dest.open("wb") as zout:
        shutil.copyfileobj(zin, zout)
    return dest
