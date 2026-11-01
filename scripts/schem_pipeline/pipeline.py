#!/usr/bin/env python3
"""Curated schematic scrape → convert → optional catalog promote.

Basics (coop, windmill, well, pens, …): prefer Bloxelizer + small block caps;
taxonomy rejects Ultimate … Survival Base/House titles for those intents.
SchemCraft / Shulkr: landmarks and furnished showpieces only.
Shulkr is **not** scraped here (manual mega ARR only).

Usage::

    PYTHONPATH=. python3 scripts/schem_pipeline/pipeline.py --sample
    PYTHONPATH=. python3 scripts/schem_pipeline/pipeline.py --sample --promote
    make schem-pipeline-sample
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.schem_pipeline.convert import ConvertError, ensure_schem  # noqa: E402
from scripts.schem_pipeline.dedup import (  # noqa: E402
    connect,
    content_seen,
    file_sha256,
    record_content_hash,
    seen_source,
    upsert_candidate,
)
from scripts.schem_pipeline.http_util import RateLimitedSession  # noqa: E402
from scripts.schem_pipeline.promote_to_catalog import promote_file  # noqa: E402
from scripts.schem_pipeline.scrapers import build_scraper  # noqa: E402
from scripts.schem_pipeline.taxonomy import (  # noqa: E402
    match_intent,
    max_blocks_for_intent,
    open_gap_ids,
)


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8"),
        ],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(ROOT / "config.yaml"),
        help="pipeline config path",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="small P0-gap sample (~config sample_limit)",
    )
    parser.add_argument(
        "--prio",
        default="P0",
        choices=("P0", "P1", "all"),
        help="gap priority band for queries",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="promote best candidate per open intent into catalog gold",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="override sample_limit",
    )
    parser.add_argument(
        "--sources",
        default="",
        help="comma list (default: config sources; schemcraft first)",
    )
    args = parser.parse_args(argv)

    cfg = load_config(Path(args.config))
    paths = cfg.get("paths") or {}
    base = ROOT
    db_path = base / paths.get("db", "db/pipeline.sqlite3")
    dl_dir = base / paths.get("downloads", "downloads")
    conv_dir = base / paths.get("converted", "downloads/converted")
    log_dir = base / paths.get("logs", "logs")
    setup_logging(log_dir)
    log = logging.getLogger("schem_pipeline")

    session = RateLimitedSession(
        user_agent=cfg.get("user_agent")
        or "NeighborhoodSchemPipeline/1.0 (+curated gap fill)",
        rate_limit_seconds=float(cfg.get("rate_limit_seconds", 1.5)),
        timeout=float(cfg.get("request_timeout_seconds", 45)),
        respect_robots=bool(cfg.get("respect_robots", True)),
    )
    con = connect(db_path)

    sources = (
        [s.strip() for s in args.sources.split(",") if s.strip()]
        if args.sources
        else list(cfg.get("sources") or ["schemcraft", "bloxelizer"])
    )
    # Keep config order (bloxelizer before schemcraft for basics).

    gap_ids = open_gap_ids(prio=args.prio)
    allowed = set(gap_ids)
    intent_queries: dict[str, list[str]] = cfg.get("intent_queries") or {}
    queries: list[tuple[str, str]] = []  # (intent_id, query)
    for intent_id in gap_ids:
        for q in intent_queries.get(intent_id, [intent_id.replace("_", " ")]):
            queries.append((intent_id, q))

    sample_limit = args.limit or int(cfg.get("sample_limit", 20))
    if not args.sample and args.limit == 0:
        sample_limit = max(sample_limit, 50)

    log.info(
        "pipeline start sources=%s open_gaps=%s sample_limit=%s promote=%s",
        sources,
        gap_ids,
        sample_limit,
        args.promote,
    )

    # Default false: private neighborhood server accepts CC-BY-NC with attribution.
    skip_nc = bool(cfg.get("skip_nc_license", False))
    min_blocks = int(cfg.get("min_blocks", 40))
    max_basic = int(cfg.get("max_blocks_basic", 80000))
    max_landmark = int(cfg.get("max_blocks_landmark", 200000))
    skip_mcstructure = bool(cfg.get("skip_mcstructure", True))

    matched: list[dict] = []
    per_intent_best: dict[str, dict] = {}

    for source_name in sources:
        try:
            scraper = build_scraper(source_name, session, cfg)
        except KeyError as exc:
            log.warning("%s", exc)
            continue
        for intent_hint, query in queries:
            if len(matched) >= sample_limit:
                break
            log.info("search %s q=%r (hint=%s)", source_name, query, intent_hint)
            try:
                results = list(scraper.search(query, limit=8))
            except Exception as exc:
                log.warning("search failed %s %r: %s", source_name, query, exc)
                continue
            for cand in results:
                if len(matched) >= sample_limit:
                    break
                if seen_source(con, cand.source, cand.source_id):
                    log.info("skip seen %s:%s", cand.source, cand.source_id)
                    continue
                if skip_nc and cand.license and "NC" in cand.license.upper():
                    upsert_candidate(
                        con,
                        {
                            "source": cand.source,
                            "source_id": cand.source_id,
                            "source_url": cand.source_url,
                            "title": cand.title,
                            "author": cand.author,
                            "license": cand.license,
                            "intent_id": None,
                            "match_score": None,
                            "match_reason": "nc_license",
                            "block_count": cand.block_count,
                            "size_x": cand.size_x,
                            "size_y": cand.size_y,
                            "size_z": cand.size_z,
                            "download_path": None,
                            "schem_path": None,
                            "content_sha256": None,
                            "status": "rejected_nc",
                            "promoted_id": None,
                            "error": "NC license",
                        },
                    )
                    continue

                m = match_intent(
                    title=cand.title,
                    tags=cand.tags,
                    description=cand.description,
                    allowed_intents=allowed,
                )
                # Require a real keyword match — never promote on query hint alone
                # (avoids coop←house / garden←cottage mis-maps).
                if m is None:
                    continue
                intent_id = m.intent_id
                score = m.score
                reason = m.reason
                # Prefer hits that agree with the query's target intent.
                if intent_id == intent_hint:
                    score += 4.0
                    reason = f"{reason}+hint:{intent_hint}"
                elif intent_hint in allowed and intent_id != intent_hint:
                    # Keep cross-hits only if score is strong.
                    if score < 20:
                        continue

                max_blocks = max_blocks_for_intent(
                    intent_id, basic=max_basic, landmark=max_landmark
                )
                if cand.block_count is not None:
                    if cand.block_count < min_blocks or cand.block_count > max_blocks:
                        upsert_candidate(
                            con,
                            {
                                "source": cand.source,
                                "source_id": cand.source_id,
                                "source_url": cand.source_url,
                                "title": cand.title,
                                "author": cand.author,
                                "license": cand.license,
                                "intent_id": intent_id,
                                "match_score": score,
                                "match_reason": reason,
                                "block_count": cand.block_count,
                                "size_x": cand.size_x,
                                "size_y": cand.size_y,
                                "size_z": cand.size_z,
                                "download_path": None,
                                "schem_path": None,
                                "content_sha256": None,
                                "status": "rejected_size",
                                "promoted_id": None,
                                "error": f"blocks={cand.block_count} outside {min_blocks}..{max_blocks}",
                            },
                        )
                        continue

                try:
                    raw_path = scraper.download(cand, dl_dir / cand.source)
                    schem_path = ensure_schem(
                        raw_path,
                        conv_dir / f"{intent_id}__{cand.source}_{cand.source_id}.schem",
                        skip_mcstructure=skip_mcstructure,
                    )
                    sha = file_sha256(schem_path)
                    if content_seen(con, sha):
                        status = "dup_content"
                        error = "duplicate sha256"
                    else:
                        record_content_hash(con, sha, cand.source, cand.source_id)
                        status = "ready"
                        error = None
                except (ConvertError, Exception) as exc:
                    upsert_candidate(
                        con,
                        {
                            "source": cand.source,
                            "source_id": cand.source_id,
                            "source_url": cand.source_url,
                            "title": cand.title,
                            "author": cand.author,
                            "license": cand.license,
                            "intent_id": intent_id,
                            "match_score": score,
                            "match_reason": reason,
                            "block_count": cand.block_count,
                            "size_x": cand.size_x,
                            "size_y": cand.size_y,
                            "size_z": cand.size_z,
                            "download_path": None,
                            "schem_path": None,
                            "content_sha256": None,
                            "status": "error",
                            "promoted_id": None,
                            "error": str(exc)[:300],
                        },
                    )
                    log.warning("download/convert fail %s: %s", cand.source_id, exc)
                    continue

                row = {
                    "source": cand.source,
                    "source_id": cand.source_id,
                    "source_url": cand.source_url,
                    "title": cand.title,
                    "author": cand.author,
                    "license": cand.license,
                    "intent_id": intent_id,
                    "match_score": score,
                    "match_reason": reason,
                    "block_count": cand.block_count,
                    "size_x": cand.size_x,
                    "size_y": cand.size_y,
                    "size_z": cand.size_z,
                    "download_path": str(raw_path),
                    "schem_path": str(schem_path),
                    "content_sha256": sha,
                    "status": status,
                    "promoted_id": None,
                    "error": error,
                }
                upsert_candidate(con, row)
                if status != "ready":
                    continue
                matched.append(row)
                prev = per_intent_best.get(intent_id)
                if prev is None or float(score) > float(prev.get("match_score") or 0):
                    per_intent_best[intent_id] = row
                log.info(
                    "ready intent=%s title=%r blocks=%s src=%s",
                    intent_id,
                    cand.title,
                    cand.block_count,
                    cand.source,
                )

    promoted = 0
    if args.promote or bool(cfg.get("promote")):
        # Still-open gaps only (re-read gold flags).
        still_open = set(open_gap_ids(prio=args.prio))
        for intent_id, row in per_intent_best.items():
            if intent_id not in still_open:
                continue
            schem = Path(row["schem_path"])
            if not schem.is_file():
                continue
            allow_arr = (row.get("license") or "") == "All-Rights-Reserved"
            result = promote_file(
                schem,
                intent_id=intent_id,
                source_url=row["source_url"],
                title=row.get("title"),
                author=row.get("author"),
                license=row.get("license"),
                allow_arr=allow_arr,
                gold=True,
            )
            if result.ok:
                promoted += 1
                upsert_candidate(
                    con,
                    {
                        **row,
                        "status": "promoted",
                        "promoted_id": result.template_id,
                        "error": None,
                    },
                )
                log.info("promoted %s ← %s", intent_id, row["source_url"])
            else:
                log.warning("promote fail %s: %s", intent_id, result.error)

    print()
    print(f"candidates_ready: {len(matched)}")
    print(f"intents_with_best: {len(per_intent_best)}")
    print(f"promoted: {promoted}")
    print(f"db: {db_path}")
    print(f"converted: {conv_dir}")
    if promoted:
        print("next: make companion-reload")
        print(
            "      make qa-refill ONLY="
            + ",".join(sorted(per_intent_best)[:12])
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
