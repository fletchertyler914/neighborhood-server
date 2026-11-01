"""MCBuild scraper — TODO: fill selectors / license checks."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .base import Candidate, Scraper


class McbuildScraper(Scraper):
    name = "mcbuild"

    def search(self, query: str, *, limit: int = 15) -> Iterator[Candidate]:
        raise NotImplementedError("mcbuild scraper stub — selectors TODO")
        yield  # pragma: no cover

    def download(self, candidate: Candidate, dest_dir: Path) -> Path:
        raise NotImplementedError("mcbuild download stub")
