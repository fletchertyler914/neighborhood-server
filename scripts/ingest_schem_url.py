#!/usr/bin/env python3
"""CLI wrapper — implementation lives in ``companion.ingest_schem``."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from companion.ingest_schem import main

if __name__ == "__main__":
    raise SystemExit(main())
