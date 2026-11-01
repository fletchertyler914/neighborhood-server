"""Source scrapers for curated schematic refill.

Priority: **SchemCraft** (CC-BY Free) → Bloxelizer → stubs.
Shulkr stays manual mega-only (not a firehose scraper).
"""

from __future__ import annotations

from .base import Candidate, Scraper
from .bloxelizer import BloxelizerScraper
from .schemcraft import SchemCraftScraper

# Scaffold stubs (selectors TODO) — importable but not in SCRAPERS until ready.
from . import abfielder, mcbuild, phantommarket, schematio  # noqa: F401

SCRAPERS: dict[str, type[Scraper]] = {
    "schemcraft": SchemCraftScraper,
    "bloxelizer": BloxelizerScraper,
}


def build_scraper(name: str, session, config: dict) -> Scraper:
    cls = SCRAPERS.get(name)
    if cls is None:
        raise KeyError(
            f"unknown or stub-only scraper {name!r}; "
            f"implemented: {sorted(SCRAPERS)}"
        )
    return cls(session=session, config=config)
