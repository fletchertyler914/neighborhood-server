#!/usr/bin/env python3
"""Apply in-game QA demotions to agent/templates/catalog.json (gold: false).

Reads append-only ``data/plugins/NeighborhoodAgent/qa-demotions.jsonl``
(written by the NeighborhoodAgent QA hoe). Last action wins per template_id.

Usage::

    make qa-apply-demotions
    # or
    PYTHONPATH=. python3 scripts/apply_qa_demotions.py
    PYTHONPATH=. python3 scripts/apply_qa_demotions.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "agent" / "templates" / "catalog.json"
DEMOTIONS_PATH = (
    REPO_ROOT / "data" / "plugins" / "NeighborhoodAgent" / "qa-demotions.jsonl"
)
MC_AGENT = os.environ.get("MC_AGENT_CONTAINER", "mc-agent")


def _fold_demotions(path: Path) -> tuple[set[str], list[dict]]:
    demoted: set[str] = set()
    rows: list[dict] = []
    if not path.is_file():
        return demoted, rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        tid = str(row.get("template_id") or "").strip()
        if not tid:
            continue
        action = str(row.get("action") or "demote").lower()
        rows.append(row)
        if action == "promote":
            demoted.discard(tid)
        else:
            demoted.add(tid)
    return demoted, rows


def apply(demoted: set[str], *, dry_run: bool) -> list[str]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    templates = catalog.get("templates") or []
    changed: list[str] = []
    missing: list[str] = []
    by_id = {str(t.get("id")): t for t in templates if t.get("id")}
    for tid in sorted(demoted):
        item = by_id.get(tid)
        if item is None:
            missing.append(tid)
            continue
        if item.get("gold") is False:
            continue
        if item.get("gold") is True or "gold" not in item:
            changed.append(tid)
            if not dry_run:
                item["gold"] = False
    if not dry_run and changed:
        CATALOG_PATH.write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if missing:
        print(f"warning: unknown template_id(s) in demotion log: {', '.join(missing)}")
    return changed


def _reload_companion() -> None:
    """Restart mc-agent so lru_cache catalog + ranker pick up gold:false."""
    try:
        subprocess.run(
            ["docker", "compose", "restart", "mc-agent"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"restarted {MC_AGENT} to reload catalog")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(
            f"note: could not restart mc-agent ({exc}); "
            "restart it when convenient so gold filters refresh",
            file=sys.stderr,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demotions",
        type=Path,
        default=DEMOTIONS_PATH,
        help="path to qa-demotions.jsonl",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would change; do not write catalog or restart",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="skip mc-agent restart after writing catalog",
    )
    args = parser.parse_args()

    demoted, rows = _fold_demotions(args.demotions)
    if not args.demotions.is_file():
        print(f"no demotion log at {args.demotions}")
        return 0
    print(f"log entries: {len(rows)} · currently demoted: {len(demoted)}")
    if demoted:
        print("  " + ", ".join(sorted(demoted)))

    changed = apply(demoted, dry_run=args.dry_run)
    if args.dry_run:
        print(f"dry-run: would set gold:false on {len(changed)} template(s)")
        for tid in changed:
            print(f"  - {tid}")
        return 0

    print(f"set gold:false on {len(changed)} template(s)")
    for tid in changed:
        print(f"  - {tid}")
    if changed and not args.no_reload:
        _reload_companion()
    elif not changed:
        print("catalog already matched demotion set (nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
