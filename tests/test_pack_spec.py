"""Template pack spec validation tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.templates.pack_spec import (
    PackManifest,
    file_content_hash,
    load_pack_manifest,
    validate_pack_manifest,
)


def test_validate_pack_rejects_bad_license(tmp_path: Path):
    pack_dir = tmp_path / "pack"
    schem_dir = pack_dir / "schematics"
    schem_dir.mkdir(parents=True)
    (schem_dir / "demo.schem").write_bytes(b"FAKE")
    manifest = {
        "pack_id": "demo_pack",
        "title": "Demo",
        "version": "1",
        "license_spdx": "CC-BY-NC-4.0",
        "attribution": "Someone",
        "author": "someone",
        "source_url": "https://example.com",
        "templates": [
            {
                "id": "demo_tpl",
                "title": "Demo",
                "category": "utility",
                "complexity": "basic",
                "schematic": "demo.schem",
                "footprint": [3, 3, 3],
            }
        ],
    }
    (pack_dir / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    m = load_pack_manifest(pack_dir / "pack.json")
    errors = validate_pack_manifest(m, pack_dir)
    assert any("license" in e.message for e in errors)


def test_validate_pack_accepts_permissive_license(tmp_path: Path):
    pack_dir = tmp_path / "pack"
    schem_dir = pack_dir / "schematics"
    schem_dir.mkdir(parents=True)
    (schem_dir / "demo.schem").write_bytes(b"FAKE")
    manifest = {
        "pack_id": "demo_pack",
        "title": "Demo",
        "version": "1",
        "license_spdx": "MIT",
        "attribution": "Someone",
        "author": "someone",
        "source_url": "https://example.com",
        "templates": [
            {
                "id": "demo_tpl",
                "title": "Demo",
                "category": "utility",
                "complexity": "basic",
                "schematic": "demo.schem",
                "footprint": [3, 3, 3],
            }
        ],
    }
    (pack_dir / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    m = load_pack_manifest(pack_dir / "pack.json")
    errors = validate_pack_manifest(m, pack_dir)
    assert errors == []


def test_file_content_hash_deterministic(tmp_path: Path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"abc")
    assert file_content_hash(p) == file_content_hash(p)
