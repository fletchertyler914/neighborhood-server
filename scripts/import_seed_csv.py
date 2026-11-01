#!/usr/bin/env python3
"""Import schem_scraper ``output/seed_schematics.csv`` into the gold catalog.

Expected columns (extras ignored)::

    title, url, source, matched_category, format_hint, scraped_at

Optional override columns (if present)::

    catalog_id, id, author, license, aliases, gold

Mapping: ``matched_category`` → catalog id via ``scripts/seed_category_map.yaml``.
Skips Create-mod / NC / mega survival-house titles for BASIC_STRUCTURE_INTENTS.

Usage::

    make import-seed-csv CSV=/path/to/seed_schematics.csv DRY_RUN=1
    PYTHONPATH=. python3 scripts/import_seed_csv.py --csv path.csv --dry-run
    PYTHONPATH=. python3 scripts/import_seed_csv.py --csv path.csv --only windmill_small
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from companion.ingest_schem import ingest_url  # noqa: E402
from scripts.schem_pipeline.taxonomy import (  # noqa: E402
    BASIC_STRUCTURE_INTENTS,
    is_survival_base_title,
)

DEFAULT_MAP = REPO_ROOT / "scripts" / "seed_category_map.yaml"

# Create-mod / schematic packs that are wrong product for kid paste.
_CREATE_MOD = re.compile(
    r"\bcreate\b|\bcreate[-_ ]mod\b|\bcreate:?\s*new\s*age\b|\bcreate\s*steam\b",
    re.I,
)
# Prefer direct .schem / known hosts; skip obvious non-schematic pages.
_PREFERRED_HOST = (
    "schemcraft.com",
    "bloxelizer.com",
    "abfielder.com",
    "mcbuild.org",
    "phantommarket",
)


def _load_category_map(path: Path) -> tuple[dict[str, str], bool]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("categories") or {}
    mapping = {str(k).strip().lower(): str(v).strip() for k, v in raw.items() if k and v}
    accept_ids = bool(data.get("accept_catalog_ids", True))
    return mapping, accept_ids


def _norm_category(value: str) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s


def resolve_catalog_id(
    row: dict[str, str],
    *,
    mapping: dict[str, str],
    accept_catalog_ids: bool,
) -> str | None:
    for key in ("catalog_id", "id"):
        explicit = (row.get(key) or "").strip()
        if explicit:
            return explicit
    cat = _norm_category(row.get("matched_category") or "")
    if not cat:
        return None
    if cat in mapping:
        return mapping[cat]
    if accept_catalog_ids and re.fullmatch(r"[a-z][a-z0-9_]*", cat):
        # Already looks like a catalog id (e.g. windmill_small).
        return cat
    return None


def skip_reason(row: dict[str, str], catalog_id: str) -> str | None:
    title = row.get("title") or ""
    url = row.get("url") or ""
    source = row.get("source") or ""
    blob = f"{title} {url} {source}"
    fmt = (row.get("format_hint") or "").strip().lower()

    if not (url or "").strip():
        return "missing url"
    if _CREATE_MOD.search(blob):
        return "create-mod / create pack"
    # Basics: reject mega survival houses by title *or* URL slug.
    if catalog_id in BASIC_STRUCTURE_INTENTS and (
        is_survival_base_title(title) or is_survival_base_title(url.replace("-", " ").replace("_", " "))
    ):
        return "survival base/house title for basic intent"
    if fmt in {"mcstructure", "nbt", "worldedit_schematic"} and not url.lower().endswith(
        (".schem", ".zip", ".litematic")
    ):
        # Still allow if URL is a page on preferred hosts (ingest resolves).
        host_ok = any(h in url.lower() for h in _PREFERRED_HOST)
        if not host_ok:
            return f"format_hint={fmt} without preferred host"
    return None


def _parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "gold"}


def _parse_aliases(value: str | None) -> list[str]:
    if not value or not str(value).strip():
        return []
    return [a.strip() for a in str(value).split(",") if a.strip()]


def _attribution(title: str, source: str, url: str) -> str:
    parts = [title.strip()] if title.strip() else []
    if source.strip():
        parts.append(f"via {source.strip()}")
    if url.strip():
        parts.append(url.strip())
    return " — ".join(parts) if parts else url


def import_row(
    row: dict[str, str],
    *,
    mapping: dict[str, str],
    accept_catalog_ids: bool,
    dry_run: bool,
    allow_arr: bool,
) -> tuple[str, str]:
    """Return (status, detail). status in ok|skip|fail."""
    catalog_id = resolve_catalog_id(
        row, mapping=mapping, accept_catalog_ids=accept_catalog_ids
    )
    if not catalog_id:
        return "skip", f"unmapped matched_category={row.get('matched_category')!r}"

    reason = skip_reason(row, catalog_id)
    if reason:
        return "skip", f"{catalog_id}: {reason}"

    url = (row.get("url") or "").strip()
    title = (row.get("title") or "").strip() or catalog_id
    source = (row.get("source") or "").strip()
    author = (row.get("author") or "").strip() or None
    license_spdx = (row.get("license") or "").strip() or None
    gold = _parse_bool(row.get("gold"), default=True)
    aliases = _parse_aliases(row.get("aliases"))

    # Provenance note from scraper `source` column (site name).
    # ingest_url accepts source_url; attribution is filled from author/title
    # unless we enrich via page HTML. Stash source in attribution via author
    # when author empty so the catalog retains a note.
    attr_note = _attribution(title, source, url)
    if not author and source:
        author = source

    if dry_run:
        extra = f" aliases={aliases}" if aliases else ""
        return (
            "ok",
            f"dry-run {catalog_id} ← {url} title={title!r} gold={gold}{extra} "
            f"note={attr_note!r}",
        )

    result = ingest_url(
        url,
        template_id=catalog_id,
        title=title,
        source_url=url,
        author=author,
        license=license_spdx,
        allow_arr=allow_arr,
        gold=gold,
        dry_run=False,
        require_allowlist=False,
    )
    if not result.ok:
        return "fail", f"{catalog_id}: {result.error}"

    # Merge optional CSV aliases + ensure provenance note when page meta empty.
    if aliases or (source and result.source_url):
        import json

        from companion.ingest_schem import catalog_path, merge_aliases

        cat_path = catalog_path()
        catalog = json.loads(cat_path.read_text(encoding="utf-8"))
        for entry in catalog.get("templates") or []:
            if entry.get("id") != catalog_id:
                continue
            if aliases:
                entry["aliases"] = merge_aliases(list(entry.get("aliases") or []), aliases)
            if source and not entry.get("attribution"):
                entry["attribution"] = attr_note
            elif source and source.lower() not in str(entry.get("attribution") or "").lower():
                entry["attribution"] = (
                    f"{entry.get('attribution') or title} (source: {source})"
                )
            break
        cat_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

    return (
        "ok",
        f"{catalog_id}: gold={result.gold} blocks={result.max_blocks} "
        f"fp={result.footprint} action={result.action}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="path to seed_schematics.csv (or compatible)",
    )
    parser.add_argument(
        "--map",
        type=Path,
        default=DEFAULT_MAP,
        help="category → catalog id YAML",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="only these catalog ids (repeatable)",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="keep going after a failed row",
    )
    parser.add_argument(
        "--allow-arr",
        action="store_true",
        help="allow All-Rights-Reserved (friends Shulkr)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="max rows to attempt (0 = all)",
    )
    args = parser.parse_args(argv)

    if not args.csv.is_file():
        print(f"error: CSV not found: {args.csv}", file=sys.stderr)
        return 2

    mapping, accept_ids = _load_category_map(args.map)
    want = set(args.only) if args.only else None

    ok = skip = fail = 0
    attempted = 0

    with args.csv.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            print("error: empty CSV", file=sys.stderr)
            return 2
        fields = {f.strip().lower(): f for f in reader.fieldnames}
        required_any = {"url"}
        if "url" not in fields:
            print(
                f"error: CSV needs a url column; got {reader.fieldnames}",
                file=sys.stderr,
            )
            return 2
        _ = required_any

        for raw in reader:
            row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            catalog_id = resolve_catalog_id(
                row, mapping=mapping, accept_catalog_ids=accept_ids
            )
            if want is not None:
                if not catalog_id or catalog_id not in want:
                    continue
            if args.limit and attempted >= args.limit:
                break
            attempted += 1
            status, detail = import_row(
                row,
                mapping=mapping,
                accept_catalog_ids=accept_ids,
                dry_run=args.dry_run,
                allow_arr=args.allow_arr,
            )
            print(f"{status:4}  {detail}")
            if status == "ok":
                ok += 1
            elif status == "skip":
                skip += 1
            else:
                fail += 1
                if not args.continue_on_error:
                    print("error: stopping after failure", file=sys.stderr)
                    break

    mode = "dry-run" if args.dry_run else "ingest"
    print(f"\ndone ({mode}): ok={ok} skip={skip} fail={fail} attempted={attempted}")
    if ok and not args.dry_run:
        print("next: make companion-reload")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
