"""Template Pack Spec — validate community and internal template packs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TEMPLATE_ID_RX = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ALLOWED_COMPLEXITY = frozenset({"basic", "common", "complex"})
_ALLOWED_LICENSES = frozenset({"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "MIT"})


@dataclass
class PackValidationError:
    path: str
    message: str


@dataclass
class PackManifest:
    pack_id: str
    title: str
    version: str
    license_spdx: str
    attribution: str
    author: str
    source_url: str
    templates: list[dict[str, Any]]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PackManifest:
        return cls(
            pack_id=str(data["pack_id"]),
            title=str(data.get("title") or data["pack_id"]),
            version=str(data.get("version") or "1"),
            license_spdx=str(data["license_spdx"]),
            attribution=str(data.get("attribution") or ""),
            author=str(data.get("author") or ""),
            source_url=str(data.get("source_url") or ""),
            templates=list(data.get("templates") or []),
        )


def load_pack_manifest(path: Path) -> PackManifest:
    with path.open(encoding="utf-8") as f:
        return PackManifest.from_dict(json.load(f))


def validate_pack_manifest(manifest: PackManifest, pack_dir: Path) -> list[PackValidationError]:
    errors: list[PackValidationError] = []
    if not _TEMPLATE_ID_RX.match(manifest.pack_id):
        errors.append(PackValidationError("pack_id", "invalid pack_id"))
    if manifest.license_spdx not in _ALLOWED_LICENSES:
        errors.append(
            PackValidationError("license_spdx", f"license not allowed: {manifest.license_spdx}")
        )
    if not manifest.templates:
        errors.append(PackValidationError("templates", "pack must include at least one template"))
    seen: set[str] = set()
    for i, tpl in enumerate(manifest.templates):
        prefix = f"templates[{i}]"
        tid = str(tpl.get("id") or "")
        if not _TEMPLATE_ID_RX.match(tid):
            errors.append(PackValidationError(f"{prefix}.id", f"invalid id: {tid!r}"))
        if tid in seen:
            errors.append(PackValidationError(f"{prefix}.id", f"duplicate id: {tid}"))
        seen.add(tid)
        complexity = str(tpl.get("complexity") or "basic")
        if complexity not in _ALLOWED_COMPLEXITY:
            errors.append(PackValidationError(f"{prefix}.complexity", f"invalid: {complexity}"))
        schematic = str(tpl.get("schematic") or f"{tid}.schem")
        if "/" in schematic or ".." in schematic:
            errors.append(PackValidationError(f"{prefix}.schematic", "path traversal"))
        schem_path = pack_dir / "schematics" / schematic
        if not schem_path.is_file():
            errors.append(PackValidationError(f"{prefix}.schematic", f"missing file: {schem_path}"))
        fp = tpl.get("footprint") or [7, 5, 7]
        if not isinstance(fp, list) or len(fp) != 3:
            errors.append(PackValidationError(f"{prefix}.footprint", "must be [w,h,d]"))
    return errors


def file_content_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def pack_to_catalog_entries(manifest: PackManifest, pack_dir: Path, *, source_id: str) -> list[dict[str, Any]]:
    """Convert validated pack templates to catalog.json rows."""

    out: list[dict[str, Any]] = []
    for tpl in manifest.templates:
        tid = str(tpl["id"])
        schematic = str(tpl.get("schematic") or f"{tid}.schem")
        schem_path = pack_dir / "schematics" / schematic
        entry = {
            "id": tid,
            "title": str(tpl.get("title") or tid.replace("_", " ").title()),
            "category": str(tpl.get("category") or "general"),
            "complexity": str(tpl.get("complexity") or "basic"),
            "tags": list(tpl.get("tags") or []),
            "aliases": list(tpl.get("aliases") or []),
            "schematic": schematic,
            "footprint": list(tpl.get("footprint") or [7, 5, 7]),
            "max_blocks": int(tpl.get("max_blocks") or 5000),
            "distance_default": int(tpl.get("distance_default") or 3),
            "follow_up": list(tpl.get("follow_up") or []),
            "fallback": tpl.get("fallback"),
            "fallback_steps": tpl.get("fallback_steps") or [],
            "source_id": source_id,
            "source_url": manifest.source_url,
            "source_ref": manifest.version,
            "license": manifest.license_spdx,
            "author": manifest.author or manifest.pack_id,
            "attribution": manifest.attribution or manifest.title,
            "content_hash": file_content_hash(schem_path) if schem_path.is_file() else "",
            "deterministic_seed_version": "1",
        }
        out.append(entry)
    return out
