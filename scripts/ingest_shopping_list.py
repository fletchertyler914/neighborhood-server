#!/usr/bin/env python3
"""Batch-ingest rows from ``scripts/ingest_shopping_list.yaml``.

User fills ``url`` fields; this runner calls ``ingest_schem_url.py`` per row.
Skips null/empty URLs. Does not mass-scrape — only listed URLs.

Usage::

    make ingest-shopping
    PYTHONPATH=. python3 scripts/ingest_shopping_list.py --dry-run
    PYTHONPATH=. python3 scripts/ingest_shopping_list.py --only house_cottage_small
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIST = REPO_ROOT / "scripts" / "ingest_shopping_list.yaml"
INGEST = REPO_ROOT / "scripts" / "ingest_schem_url.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", type=Path, default=DEFAULT_LIST, help="YAML shopping list")
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
        "--reload",
        action="store_true",
        help="run make companion-reload after successful ingest(s)",
    )
    args = parser.parse_args(argv)

    data = yaml.safe_load(args.list.read_text(encoding="utf-8")) or {}
    items = list(data.get("items") or [])
    if args.only:
        want = set(args.only)
        items = [it for it in items if str(it.get("id") or it.get("intent")) in want]

    ran = 0
    ok = 0
    skipped = 0
    failed = 0

    for item in items:
        tid = str(item.get("id") or item.get("intent") or "").strip()
        url = item.get("url")
        if url is None or str(url).strip() in {"", "null", "None"}:
            print(f"skip  {tid or '?'}: no url")
            skipped += 1
            continue
        if not tid:
            print("skip  <missing id>")
            skipped += 1
            continue

        cmd = [
            sys.executable,
            str(INGEST),
            "--url",
            str(url).strip(),
            "--id",
            tid,
        ]
        if item.get("title"):
            cmd.extend(["--title", str(item["title"])])
        if item.get("source_url"):
            cmd.extend(["--source-url", str(item["source_url"])])
        if item.get("author"):
            cmd.extend(["--author", str(item["author"])])
        if item.get("license"):
            cmd.extend(["--license", str(item["license"])])
        if item.get("allow_arr"):
            cmd.append("--allow-arr")
        if item.get("allow_rejected_license"):
            cmd.append("--allow-rejected-license")
        if args.dry_run:
            cmd.append("--dry-run")

        print(f"\n=== ingest {tid} ===")
        print(" ", " ".join(cmd))
        ran += 1
        proc = subprocess.run(cmd, cwd=REPO_ROOT)
        if proc.returncode == 0:
            ok += 1
        else:
            failed += 1
            if not args.continue_on_error:
                print(f"error: stopping after failure on {tid}", file=sys.stderr)
                break

    print(f"\ndone: ran={ran} ok={ok} failed={failed} skipped={skipped}")
    if args.reload and ok and not args.dry_run:
        subprocess.run(["make", "companion-reload"], cwd=REPO_ROOT, check=False)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
