"""Scraper interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class Candidate:
    source: str
    source_id: str
    source_url: str
    title: str
    author: str = ""
    license: str | None = None
    attribution: str = ""
    block_count: int | None = None
    size_x: int | None = None
    size_y: int | None = None
    size_z: int | None = None
    tags: list[str] = field(default_factory=list)
    description: str = ""
    download_hint: str = ""  # format hint: schem|litematic|unknown
    extra: dict[str, Any] = field(default_factory=dict)


class Scraper:
    name = "base"

    def __init__(self, *, session, config: dict) -> None:
        self.session = session
        self.config = config

    def search(self, query: str, *, limit: int = 15) -> Iterator[Candidate]:
        raise NotImplementedError

    def download(self, candidate: Candidate, dest_dir: Path) -> Path:
        raise NotImplementedError
