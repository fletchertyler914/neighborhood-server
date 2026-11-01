"""Schemat.io scraper — TODO: fill selectors / API.

Not enabled by default. Search https://schemat.io/ for P0 keywords, prefer
native .schem, store attribution + license from page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .base import Candidate, Scraper


class SchematioScraper(Scraper):
    name = "schematio"

    def search(self, query: str, *, limit: int = 15) -> Iterator[Candidate]:
        # TODO: page selectors for listing cards + license badge
        raise NotImplementedError(
            "schematio scraper stub — implement listing/detail selectors before enable"
        )
        yield  # pragma: no cover

    def download(self, candidate: Candidate, dest_dir: Path) -> Path:
        raise NotImplementedError("schematio download stub")
