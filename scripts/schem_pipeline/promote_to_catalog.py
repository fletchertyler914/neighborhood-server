"""Promote a converted .schem into the gold catalog via companion.ingest_schem."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from companion.ingest_schem import IngestResult, ingest_url  # noqa: E402


def promote_file(
    schem_path: Path,
    *,
    intent_id: str,
    source_url: str,
    title: str | None = None,
    author: str | None = None,
    license: str | None = None,
    allow_arr: bool = False,
    gold: bool = True,
) -> IngestResult:
    return ingest_url(
        str(schem_path.resolve()),
        template_id=intent_id,
        title=title,
        source_url=source_url,
        author=author,
        license=license,
        allow_arr=allow_arr,
        gold=gold,
        require_allowlist=False,
    )
