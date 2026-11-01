"""SchemCraft scraper — landmarks / furnished Free pages.

Uses public HTML page + ``/download`` zip (same path as companion.ingest_schem).
Tags CC-BY-NC / CC-BY-NC-SA when detectable (allowed for private server ingest
with attribution). Prefer CC-BY when bulk-filling gaps.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from .base import Candidate, Scraper

_LICENSE_NC_SA = re.compile(
    r"NonCommercial-ShareAlike|CC-BY-NC-SA|BY-NC-SA|licenses/by-nc-sa",
    re.I,
)
_LICENSE_NC = re.compile(r"NonCommercial|CC-BY-NC|BY-NC|licenses/by-nc", re.I)
_LICENSE_BY = re.compile(
    r"Creative Commons Attribution 4\.0|CC-BY(?!-)|licenses/by/4",
    re.I,
)
_LICENSE_BY_SA = re.compile(r"Attribution-ShareAlike|CC-BY-SA|licenses/by-sa", re.I)
_LICENSE_CC0 = re.compile(r"CC0|Creative Commons Zero", re.I)


class SchemCraftScraper(Scraper):
    name = "schemcraft"

    def __init__(self, *, session, config: dict) -> None:
        super().__init__(session=session, config=config)
        sc = config.get("schemcraft") or {}
        self.site_base = sc.get("site_base", "https://www.schemcraft.com").rstrip("/")
        self.max_sitemap = int(sc.get("max_sitemap_urls", 200))

    def search(self, query: str, *, limit: int = 15) -> Iterator[Candidate]:
        """Match query tokens against SchemCraft sitemap + listing slug titles."""
        q = (query or "").strip().lower()
        tokens = [t for t in re.split(r"[^a-z0-9]+", q) if len(t) >= 3]
        if not tokens:
            return
        slugs = self._candidate_slugs()
        scored: list[tuple[int, str]] = []
        for slug in slugs:
            score = sum(3 for t in tokens if t in slug)
            # Prefer multi-token hits.
            if score > 0:
                scored.append((score, slug))
        scored.sort(key=lambda x: (-x[0], x[1]))
        seen: set[str] = set()
        for _score, slug in scored:
            if slug in seen:
                continue
            seen.add(slug)
            cand = self._page_candidate(slug)
            if cand is None:
                continue
            yield cand
            if len(seen) >= limit:
                break

    def _candidate_slugs(self) -> list[str]:
        # Sitemap is small (~70–100 schematic URLs) and robots-allowed.
        try:
            body, _, _ = self.session.get_bytes(f"{self.site_base}/sitemap.xml")
            root = ET.fromstring(body)
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            locs = [
                (e.text or "")
                for e in root.findall("s:url/s:loc", ns)
                if e is not None and e.text
            ]
            # Index?
            if any("sitemap" in u and u.endswith(".xml") for u in locs) and not any(
                "/schematics/" in u for u in locs
            ):
                locs = []
                for idx in [
                    e.text
                    for e in root.findall("s:sitemap/s:loc", ns)
                    if e is not None and e.text
                ][:3]:
                    b2, _, _ = self.session.get_bytes(idx)
                    r2 = ET.fromstring(b2)
                    locs.extend(
                        e.text or ""
                        for e in r2.findall("s:url/s:loc", ns)
                        if e is not None and e.text
                    )
        except Exception:
            locs = []
        slugs: list[str] = []
        for loc in locs:
            if "/schematics/" not in loc:
                continue
            slug = Path(urlparse(loc).path.rstrip("/")).name
            if slug and slug not in {"schematics", "download"}:
                slugs.append(slug)
            if len(slugs) >= self.max_sitemap:
                break
        if slugs:
            return slugs
        # Fallback: HTML listing first page.
        try:
            html, _, _ = self.session.get_bytes(f"{self.site_base}/schematics")
            text = html.decode("utf-8", "replace")
            return list(
                dict.fromkeys(re.findall(r"/schematics/([a-z0-9\-]+)", text))
            )[: self.max_sitemap]
        except Exception:
            return []

    def _page_candidate(self, slug: str) -> Candidate | None:
        url = f"{self.site_base}/schematics/{slug}"
        try:
            html_b, final, _ = self.session.get_bytes(url)
        except Exception:
            return None
        html = html_b.decode("utf-8", "replace")
        title_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
        title = (
            re.sub(r"<[^>]+>", "", unescape(title_m.group(1))).strip()
            if title_m
            else slug.replace("-", " ")
        )
        author = ""
        auth_m = re.search(
            r"<dt>\s*Author\s*</dt>\s*<dd>(.*?)</dd>", html, re.I | re.S
        )
        if auth_m:
            author = re.sub(r"<[^>]+>", "", unescape(auth_m.group(1))).strip()
        lic_raw = ""
        lic_m = re.search(
            r"<dt>\s*License\s*</dt>\s*<dd>(.*?)</dd>", html, re.I | re.S
        )
        if lic_m:
            lic_raw = re.sub(r"<[^>]+>", "", unescape(lic_m.group(1))).strip()
        license_spdx = None
        blob = f"{lic_raw}\n{html[:12000]}"
        if _LICENSE_NC_SA.search(blob):
            license_spdx = "CC-BY-NC-SA-4.0"
        elif _LICENSE_NC.search(lic_raw) or _LICENSE_NC.search(html[:8000]):
            license_spdx = "CC-BY-NC-4.0"
        elif _LICENSE_BY_SA.search(lic_raw):
            license_spdx = "CC-BY-SA-4.0"
        elif _LICENSE_CC0.search(lic_raw):
            license_spdx = "CC0-1.0"
        elif _LICENSE_BY.search(lic_raw) or _LICENSE_BY.search(html[:12000]):
            license_spdx = "CC-BY-4.0"

        blocks = None
        bm = re.search(r"([\d,]+)\s*blocks", html, re.I)
        if bm:
            blocks = int(bm.group(1).replace(",", ""))
        dims = re.search(r"(\d+)\s*[x×]\s*(\d+)\s*[x×]\s*(\d+)", html)
        size = (
            (int(dims.group(1)), int(dims.group(2)), int(dims.group(3)))
            if dims
            else (None, None, None)
        )
        return Candidate(
            source=self.name,
            source_id=f"schemcraft_{slug}",
            source_url=final.split("?")[0],
            title=title,
            author=author,
            license=license_spdx,
            attribution=(
                f"{title} by {author} ({license_spdx or 'unknown'}) — via SchemCraft"
                if author
                else f"{title} — via SchemCraft"
            ),
            block_count=blocks,
            size_x=size[0],
            size_y=size[1],
            size_z=size[2],
            tags=[],
            description="",
            download_hint="schem",
            extra={"slug": slug, "download_url": url.rstrip("/") + "/download"},
        )

    def download(self, candidate: Candidate, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dl = (candidate.extra or {}).get("download_url") or (
            candidate.source_url.rstrip("/") + "/download"
        )
        body, final, ctype = self.session.get_bytes(str(dl))
        # Zip or gzip schem.
        suffix = ".zip"
        fl = final.lower().split("?", 1)[0]
        if fl.endswith(".schem") or (
            body[:2] == b"\x1f\x8b" and "zip" not in (ctype or "").lower()
        ):
            suffix = ".schem"
        elif body[:2] == b"PK" or "zip" in (ctype or "").lower():
            suffix = ".zip"
        slug = str((candidate.extra or {}).get("slug") or candidate.source_id)
        out = dest_dir / f"{candidate.source}_{slug}{suffix}"
        out.write_bytes(body)
        return out
