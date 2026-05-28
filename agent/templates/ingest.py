"""Strict allowlist template ingestion and catalog merge."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from agent.templates import catalog as template_catalog
from agent.templates.corpus_sprint_entries import corpus_sprint_entries
from agent.templates.gold_entries import gold_template_entries
from agent.templates.pack_spec import (
    PackManifest,
    load_pack_manifest,
    pack_to_catalog_entries,
    validate_pack_manifest,
)

_REPO = Path(__file__).resolve().parents[2]
_TEMPLATES_DIR = Path(__file__).resolve().parent
_SOURCES_PATH = _TEMPLATES_DIR / "sources.yaml"
_POLICY_PATH = _TEMPLATES_DIR / "license_policy.yaml"
_QUARANTINE = _TEMPLATES_DIR / "quarantine"
_INGESTED = _TEMPLATES_DIR / "ingested"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_sources() -> list[dict[str, Any]]:
    data = load_yaml(_SOURCES_PATH)
    return list(data.get("sources") or [])


def allowed_licenses() -> set[str]:
    policy = load_yaml(_POLICY_PATH)
    return set(policy.get("inbound_allowed_spdx") or [])


def merge_catalog_entries(entries: list[dict[str, Any]], *, replace_ids: bool = True) -> int:
    raw = template_catalog.load_catalog()
    existing = {str(t["id"]): t for t in (raw.get("templates") or [])}
    added = 0
    for entry in entries:
        tid = str(entry["id"])
        if tid in existing and not replace_ids:
            continue
        existing[tid] = entry
        added += 1
    raw["templates"] = sorted(existing.values(), key=lambda x: x["id"])
    path = template_catalog.catalog_path()
    with path.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)
        f.write("\n")
    template_catalog.reload_catalog()
    return added


def apply_gold_corpus() -> int:
    base_ids = {t["id"] for t in (template_catalog.load_catalog().get("templates") or [])}
    gold = gold_template_entries()
    new = [e for e in gold if e["id"] not in base_ids]
    return merge_catalog_entries(new, replace_ids=True)


def apply_corpus_sprint() -> int:
    """Merge corpus sprint rows (target 100+ catalog entries)."""

    existing = {str(t["id"]) for t in (template_catalog.load_catalog().get("templates") or [])}
    sprint = [e for e in corpus_sprint_entries() if e["id"] not in existing]
    return merge_catalog_entries(sprint, replace_ids=True)


def ingest_enabled_pack_dirs(packs_root: Path | None = None) -> list[dict[str, Any]]:
    """Ingest every ``pack.json`` under ``agent/templates/packs/`` for enabled sources."""

    root = packs_root or (_TEMPLATES_DIR / "packs")
    if not root.is_dir():
        return []
    enabled = {s["source_id"] for s in load_sources() if s.get("enabled")}
    results: list[dict[str, Any]] = []
    for pack_dir in sorted(root.iterdir()):
        if not pack_dir.is_dir():
            continue
        manifest_path = pack_dir / "pack.json"
        if not manifest_path.is_file():
            continue
        with manifest_path.open(encoding="utf-8") as f:
            pack_raw = json.load(f)
        sid = str(pack_raw.get("source_id") or pack_dir.name)
        if sid not in enabled:
            results.append({"ok": False, "pack": pack_dir.name, "skipped": "source_disabled"})
            continue
        results.append(ingest_pack(pack_dir, source_id=sid))
    return results


def ingest_pack(pack_dir: Path, *, source_id: str) -> dict[str, Any]:
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing pack.json in {pack_dir}")
    manifest = load_pack_manifest(manifest_path)
    errors = validate_pack_manifest(manifest, pack_dir)
    if errors:
        qdir = _QUARANTINE / source_id
        qdir.mkdir(parents=True, exist_ok=True)
        report = {"errors": [e.__dict__ for e in errors]}
        (qdir / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return {"ok": False, "errors": report}
    entries = pack_to_catalog_entries(manifest, pack_dir, source_id=source_id)
    n = merge_catalog_entries(entries)
    out_dir = _INGESTED / source_id
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_path, out_dir / "pack.json")
    return {"ok": True, "merged": n, "pack_id": manifest.pack_id}


def generate_attribution(path: Path | None = None) -> Path:
    path = path or (_TEMPLATES_DIR / "ATTRIBUTION.md")
    lines = ["# Template attributions\n"]
    raw = template_catalog.load_catalog()
    by_source: dict[str, list[dict[str, Any]]] = {}
    for t in raw.get("templates") or []:
        sid = str(t.get("source_id") or "unknown")
        by_source.setdefault(sid, []).append(t)
    for sid, rows in sorted(by_source.items()):
        lines.append(f"\n## {sid}\n")
        for t in sorted(rows, key=lambda x: x["id"]):
            attr = t.get("attribution") or t.get("title")
            lic = t.get("license") or ""
            lines.append(f"- `{t['id']}` — {attr} ({lic})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Template ingestion")
    parser.add_argument("--apply-gold", action="store_true", help="Merge gold corpus into catalog.json")
    parser.add_argument(
        "--apply-corpus-sprint",
        action="store_true",
        help="Merge corpus sprint entries (55 -> 100+)",
    )
    parser.add_argument(
        "--ingest-packs",
        action="store_true",
        help="Ingest all packs under agent/templates/packs/ for enabled sources",
    )
    parser.add_argument("--pack-dir", type=Path, help="Ingest a template pack directory")
    parser.add_argument("--source-id", type=str, default="")
    parser.add_argument("--attribution", action="store_true")
    args = parser.parse_args()
    if args.apply_gold:
        n = apply_gold_corpus()
        print(f"merged {n} gold templates")
    if args.apply_corpus_sprint:
        n = apply_corpus_sprint()
        print(f"merged {n} corpus sprint templates")
    if args.ingest_packs:
        for row in ingest_enabled_pack_dirs():
            print(json.dumps(row, indent=2))
    if args.pack_dir:
        sid = args.source_id or args.pack_dir.name
        print(json.dumps(ingest_pack(args.pack_dir, source_id=sid), indent=2))
    if args.attribution:
        p = generate_attribution()
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
