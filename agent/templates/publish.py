"""Publish internal templates as CC-BY template packs."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.templates import catalog as template_catalog
from agent.templates.pack_spec import file_content_hash

_PUBLISHED = Path(__file__).resolve().parent / "published"
_CC_BY = "CC-BY-4.0"


def build_publish_pack(
    template_ids: list[str],
    *,
    pack_id: str = "neighborhood_gold",
    version: str | None = None,
) -> Path:
    version = version or datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = _PUBLISHED / f"{pack_id}-{version}"
    schem_dir = out_dir / "schematics"
    schem_dir.mkdir(parents=True, exist_ok=True)
    templates: list[dict[str, Any]] = []
    for tid in template_ids:
        meta = template_catalog.find_template(tid)
        local = template_catalog.schematic_repo_path(meta)
        if local.is_file():
            shutil.copy2(local, schem_dir / meta.schematic)
            content_hash = file_content_hash(local)
        else:
            content_hash = ""
        templates.append(
            {
                "id": meta.id,
                "title": meta.title,
                "category": meta.category,
                "complexity": meta.complexity,
                "tags": list(meta.tags),
                "aliases": list(meta.aliases),
                "schematic": meta.schematic,
                "footprint": list(meta.footprint),
                "max_blocks": meta.max_blocks,
                "distance_default": meta.distance_default,
                "follow_up": list(meta.follow_up),
                "content_hash": content_hash,
            }
        )
    manifest = {
        "pack_id": pack_id,
        "title": "Neighborhood Gold Templates",
        "version": version,
        "license_spdx": _CC_BY,
        "attribution": "Neighborhood Minecraft Server contributors",
        "author": "neighborhood",
        "source_url": "https://github.com/neighborhood-server/templates",
        "templates": templates,
    }
    (out_dir / "pack.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out_dir / "LICENSE").write_text(
        "Creative Commons Attribution 4.0 International (CC BY 4.0)\n"
        "https://creativecommons.org/licenses/by/4.0/\n",
        encoding="utf-8",
    )
    index_path = _PUBLISHED / "index.json"
    index: dict[str, Any] = {}
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    index[pack_id] = {"version": version, "path": str(out_dir.relative_to(_PUBLISHED))}
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    changelog = _PUBLISHED / "CHANGELOG.md"
    line = f"- {version}: published {len(template_ids)} templates ({pack_id})\n"
    if changelog.is_file():
        changelog.write_text(changelog.read_text(encoding="utf-8") + line, encoding="utf-8")
    else:
        changelog.write_text("# Published template packs\n\n" + line, encoding="utf-8")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish CC-BY template pack")
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--pack-id", default="neighborhood_gold")
    args = parser.parse_args()
    out = build_publish_pack(args.ids, pack_id=args.pack_id)
    print(f"published to {out}")


if __name__ == "__main__":
    main()
