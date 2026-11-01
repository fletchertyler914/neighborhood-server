"""PhantomMarket scraper — TODO: fill selectors / license checks."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .base import Candidate, Scraper


class PhantommarketScraper(Scraper):
    name = "phantommarket"

    def search(self, query: str, *, limit: int = 15) -> Iterator[Candidate]:
        raise NotImplementedError("phantommarket scraper stub — selectors TODO")
        yield  # pragma: no cover

    def download(self, candidate: Candidate, dest_dir: Path) -> Path:
        raise NotImplementedError("phantommarket download stub")
