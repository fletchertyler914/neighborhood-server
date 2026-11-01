"""Abfielder scraper — TODO: fill selectors.

Many pages are .litematic with on-site convert-to-.schem. Confirm license per
page before promote (often unspecified → stage only).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .base import Candidate, Scraper


class AbfielderScraper(Scraper):
    name = "abfielder"

    def search(self, query: str, *, limit: int = 15) -> Iterator[Candidate]:
        # TODO: ProductDetails listing + free download link selectors
        raise NotImplementedError(
            "abfielder scraper stub — implement free .schem/.litematic selectors"
        )
        yield  # pragma: no cover

    def download(self, candidate: Candidate, dest_dir: Path) -> Path:
        raise NotImplementedError("abfielder download stub")
