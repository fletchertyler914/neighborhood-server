"""Bloxelizer public API scraper (search + CDN download with render_token)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator
from urllib.parse import quote

from .base import Candidate, Scraper


class BloxelizerScraper(Scraper):
    name = "bloxelizer"

    def __init__(self, *, session, config: dict) -> None:
        super().__init__(session=session, config=config)
        bx = config.get("bloxelizer") or {}
        self.api_base = bx.get("api_base", "https://api.bloxelizer.com/api").rstrip("/")
        self.site_base = bx.get("site_base", "https://bloxelizer.com").rstrip("/")
        self.cdn_tmpl = bx.get(
            "cdn_schematic",
            "https://bloxelizer.com/cdn/schematics/{id}?t={token}",
        )
        self.page_size = int(bx.get("page_size", 15))
        self.max_pages = int(bx.get("max_pages_per_query", 2))

    def search(self, query: str, *, limit: int = 15) -> Iterator[Candidate]:
        seen: set[str] = set()
        yielded = 0
        page = 1
        while yielded < limit and page <= self.max_pages:
            url = (
                f"{self.api_base}/schematics/search"
                f"?q={quote(query)}&limit={self.page_size}&page={page}"
            )
            payload = self.session.get_json(url)
            items = payload.get("data") or []
            if not items:
                break
            for item in items:
                sid = str(item.get("id") or "")
                if not sid or sid in seen:
                    continue
                seen.add(sid)
                slug = str(item.get("slug") or sid)
                tags = []
                for t in item.get("tags") or []:
                    if isinstance(t, dict):
                        tags.append(str(t.get("slug") or t.get("name") or ""))
                    else:
                        tags.append(str(t))
                # License rarely declared on Bloxelizer; keep None (unknown).
                # NC skip happens later if license text appears in description.
                desc = str(item.get("description") or "")
                lic = None
                low = desc.lower()
                if "noncommercial" in low or "cc-by-nc" in low or "cc by-nc" in low:
                    lic = "CC-BY-NC-4.0"
                elif "cc-by-sa" in low or "creativecommons.org/licenses/by-sa" in low:
                    lic = "CC-BY-SA-4.0"
                elif "cc-by" in low or "creativecommons.org/licenses/by/" in low:
                    lic = "CC-BY-4.0"
                elif "cc0" in low or "public domain" in low:
                    lic = "CC0-1.0"

                author = str(item.get("username") or "")
                title = str(item.get("name") or slug)
                yield Candidate(
                    source=self.name,
                    source_id=sid,
                    source_url=f"{self.site_base}/schematics/{slug}",
                    title=title,
                    author=author,
                    license=lic,
                    attribution=(
                        f"{title} by {author} — via Bloxelizer"
                        if author
                        else f"{title} — via Bloxelizer"
                    ),
                    block_count=int(item["block_count"])
                    if item.get("block_count") is not None
                    else None,
                    size_x=int(item["size_x"]) if item.get("size_x") is not None else None,
                    size_y=int(item["size_y"]) if item.get("size_y") is not None else None,
                    size_z=int(item["size_z"]) if item.get("size_z") is not None else None,
                    tags=[t for t in tags if t],
                    description=desc,
                    download_hint="litematic",
                    extra={"slug": slug, "flavor": item.get("flavor")},
                )
                yielded += 1
                if yielded >= limit:
                    break
            if len(items) < self.page_size:
                break
            page += 1

    def _render_token(self, candidate: Candidate) -> str:
        slug = (candidate.extra or {}).get("slug")
        if slug:
            meta = self.session.get_json(f"{self.api_base}/schematics/slug/{slug}")
        else:
            meta = self.session.get_json(f"{self.api_base}/schematics/{candidate.source_id}")
        token = meta.get("render_token")
        if not token:
            raise RuntimeError(f"no render_token for {candidate.source_id}")
        # Refresh block count / sizes if missing.
        if candidate.block_count is None and meta.get("block_count") is not None:
            candidate.block_count = int(meta["block_count"])
        return str(token)

    def download(self, candidate: Candidate, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        token = self._render_token(candidate)
        url = self.cdn_tmpl.format(id=candidate.source_id, token=token)
        body, _final, _ctype = self.session.get_bytes(url)
        # CDN serves gzip NBT litematic (often without extension).
        out = dest_dir / f"{candidate.source}_{candidate.source_id}.litematic"
        out.write_bytes(body)
        return out
