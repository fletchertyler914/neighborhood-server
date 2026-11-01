#!/usr/bin/env python3
"""Ingest one schematic URL (or local file) into the gold template library.

Downloads SchemCraft / Bloxelizer / Shulkr / direct ``.schem`` / ``.zip`` links,
extracts or converts when needed, writes ``agent/templates/schematics/<id>.schem``,
and upserts a gold row in ``catalog.json`` (aliases, footprint, provenance —
best effort). Bloxelizer pages: API slug → CDN ``.litematic`` → Sponge ``.schem``
(``Schematic`` NBT root). Undeclared Bloxelizer license defaults to CC-BY-4.0.

Usage::

    PYTHONPATH=. python3 scripts/ingest_schem_url.py \\
      --url 'https://www.schemcraft.com/schematics/fantasy-medieval-survival-house' \\
      --id house_cottage_small

    make ingest-schem URL='https://…' ID=house_cottage_small TITLE='Small cottage'

FAWE paste requires Sponge ``.schem``. ``.litematic`` is converted in-process via
``scripts/schem_pipeline/convert.py`` (litemapy + varint-safe BlockData).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = (
    "NeighborhoodIngest/1.0 (+https://github.com/neighborhood-server; "
    "curated single-asset fetch)"
)

# Hosts allowed for in-game / ops ingest (schemcraft / bloxelizer / shulkr).
ALLOWLIST_HOSTS = (
    "www.schemcraft.com",
    "schemcraft.com",
    "www.bloxelizer.com",
    "bloxelizer.com",
    "api.bloxelizer.com",
    "www.shulkr.com",
    "shulkr.com",
    "api.shulkr.com",
)

BLOXELIZER_API = "https://api.bloxelizer.com/api"
BLOXELIZER_CDN = "https://bloxelizer.com/cdn/schematics/{id}?t={token}"
# Bloxelizer pages rarely declare SPDX; friends-server default when undeclared.
BLOXELIZER_DEFAULT_LICENSE = "CC-BY-4.0"


def catalog_path() -> Path:
    import os

    candidates = [
        Path(os.environ["AGENT_CATALOG_PATH"]) if os.environ.get("AGENT_CATALOG_PATH") else None,
        Path("/app/assets/catalog.json"),
        REPO_ROOT / "agent" / "templates" / "catalog.json",
    ]
    for path in candidates:
        if path is not None and path.is_file():
            return path
    # Default write target on host/dev.
    return REPO_ROOT / "agent" / "templates" / "catalog.json"


def schem_dir() -> Path:
    import os

    candidates = [
        Path(os.environ["AGENT_SCHEM_DIR"]) if os.environ.get("AGENT_SCHEM_DIR") else None,
        Path("/app/assets/schematics"),
        REPO_ROOT / "agent" / "templates" / "schematics",
    ]
    for path in candidates:
        if path is not None and path.is_dir():
            return path
    out = REPO_ROOT / "agent" / "templates" / "schematics"
    out.mkdir(parents=True, exist_ok=True)
    return out


def seed_bak_dir() -> Path:
    return schem_dir() / "_seed_bak"


# Extra NL phrases merged on ingest (kid asks / eval staples). Title-derived
# aliases still apply; catalog upserts keep prior aliases.
EXTRA_ALIASES: dict[str, list[str]] = {
    "house_cottage_small": [
        "house",
        "cottage",
        "tiny house",
        "small house",
        "little house",
        "small cottage",
        "build me a house",
        "build a house",
        "make a house",
    ],
    "cabin_log": [
        "cabin",
        "log cabin",
        "wood cabin",
        "wooden cabin",
        "spruce cabin",
        "build me a cabin",
        "build a log cabin",
    ],
    "treehouse_oak": [
        "treehouse",
        "tree house",
        "oak treehouse",
        "build me a treehouse",
    ],
    "castle_small_keep": [
        "castle",
        "little castle",
        "small castle",
        "keep",
        "starter castle",
        "build me a castle",
    ],
    "fishing_hut": [
        "fishing hut",
        "fisherman cottage",
        "fisherman hut",
        "fishing shack",
    ],
    "bakery_small": [
        "bakery",
        "bread shop",
        "bakehouse",
        "build me a bakery",
    ],
    "cottage_medium": [
        "medium cottage",
        "bigger cottage",
        "family cottage",
        "fairy tale cottage",
    ],
    "church_small": [
        "church",
        "chapel",
        "stave church",
        "build me a church",
    ],
    "inn_small": [
        "inn",
        "castle inn",
        "build me an inn",
    ],
    "library_small": [
        "library",
        "bookstore",
        "book shop",
        "build me a library",
    ],
}


def backup_seed_schem(dest: Path) -> Path | None:
    """If replacing an existing schem, keep one seed/junk backup under _seed_bak/."""
    if not dest.is_file() or dest.stat().st_size == 0:
        return None
    # Skip re-backup when dest already looks like a community refill (>8 KiB).
    # Seed junk in this repo is typically a few hundred bytes.
    if dest.stat().st_size > 8192:
        return None
    bak_dir = seed_bak_dir()
    bak_dir.mkdir(parents=True, exist_ok=True)
    bak = bak_dir / f"{dest.stem}.seed-bak.schem"
    if bak.is_file():
        return bak
    shutil.copy2(dest, bak)
    return bak

STOPWORDS = {
    "a",
    "an",
    "the",
    "of",
    "and",
    "or",
    "for",
    "to",
    "by",
    "with",
    "in",
    "on",
    "at",
    "from",
    "small",
    "large",
    "tiny",
    "little",
    "big",
    "medium",
    "ultimate",
    "survival",
    "base",
    "schematic",
    "build",
    "minecraft",
}

LICENSE_MAP = (
    (re.compile(r"CC0|Creative Commons Zero", re.I), "CC0-1.0"),
    # NC-SA before SA / NC so Attribution-NonCommercial-ShareAlike classifies correctly.
    (
        re.compile(
            r"CC-BY-NC-SA|Attribution-NonCommercial-ShareAlike|by-nc-sa",
            re.I,
        ),
        "CC-BY-NC-SA-4.0",
    ),
    (re.compile(r"CC-BY-SA|Attribution-ShareAlike|by-sa", re.I), "CC-BY-SA-4.0"),
    (
        re.compile(
            r"CC-BY-NC|Attribution-NonCommercial|NonCommercial|by-nc",
            re.I,
        ),
        "CC-BY-NC-4.0",
    ),
    (re.compile(r"CC-BY-ND|NoDeriv|by-nd", re.I), "CC-BY-ND-4.0"),
    (
        re.compile(r"CC-BY(?!-)|Creative Commons Attribution 4\.0|Attribution 4\.0", re.I),
        "CC-BY-4.0",
    ),
    (re.compile(r"\bMIT\b"), "MIT"),
    (re.compile(r"All Rights Reserved|ARR\b", re.I), "All-Rights-Reserved"),
)

# Private neighborhood server: CC-BY-NC (+ SA) OK with attribution stored locally.
# Still reject ND / proprietary / unknown. Prefer CC-BY when bulk-scraping.
REJECTED_LICENSE_MARKERS = ("ND", "NOASSERTION", "PROPRIETARY")
ALLOWED_SPDX = {
    "CC0-1.0",
    "CC-BY-4.0",
    "CC-BY-SA-4.0",
    "CC-BY-NC-4.0",
    "CC-BY-NC-SA-4.0",
    "CC-BY-NC-3.0",
    "CC-BY-NC-SA-3.0",
    "MIT",
}


class IngestError(RuntimeError):
    """User-facing ingest failure."""


def http_get(url: str, *, timeout: int = 60) -> tuple[bytes, str, str]:
    """GET url → (body, final_url, content_type). Prefer httpx, else curl."""
    try:
        import httpx

        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content, str(resp.url), resp.headers.get("content-type", "")
    except Exception as httpx_exc:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = Path(tmp.name)
        try:
            cmd = [
                "curl",
                "-fsSL",
                "-A",
                USER_AGENT,
                "-o",
                str(path),
                "-w",
                "%{url_effective}\n%{content_type}",
                url,
            ]
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode != 0:
                raise IngestError(
                    f"download failed ({proc.returncode}): {url}\n"
                    f"{(proc.stderr or '').strip()}\n(httpx: {httpx_exc})"
                )
            meta = (proc.stdout or "").strip().splitlines()
            final = meta[0] if meta else url
            ctype = meta[1] if len(meta) > 1 else ""
            return path.read_bytes(), final, ctype
        finally:
            path.unlink(missing_ok=True)


def slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:64] or "template"


def aliases_from_title(title: str) -> list[str]:
    title = re.sub(r"\s+", " ", title.strip())
    if not title:
        return []
    lower = title.lower()
    words = [w for w in re.split(r"[^a-z0-9]+", lower) if w and w not in STOPWORDS]
    phrases: list[str] = [lower]
    if words:
        joined = " ".join(words)
        if joined != lower:
            phrases.append(joined)
        if len(words) >= 2:
            phrases.append(" ".join(words[:2]))
        phrases.append(words[0])
    core = phrases[1] if len(phrases) > 1 else phrases[0]
    for wrap in (
        f"little {core}",
        f"small {core}",
        f"build a {core}",
        f"make a {core}",
        f"build me a {core}",
        f"{core} please",
    ):
        phrases.append(wrap)
    out: list[str] = []
    seen: set[str] = set()
    for p in phrases:
        p = p.strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def normalize_license(raw: str | None) -> str | None:
    if not raw:
        return None
    text = unescape(raw).strip()
    for pat, spdx in LICENSE_MAP:
        if pat.search(text):
            return spdx
    if text.startswith("http") and "creativecommons.org/licenses/" in text:
        m = re.search(r"licenses/([a-z0-9\-]+)/([0-9.]+)", text, re.I)
        if m:
            return normalize_license(f"CC-{m.group(1).upper()}-{m.group(2)}")
    return text[:80] if text else None


def license_rejected(spdx: str | None) -> bool:
    if not spdx:
        return True
    if spdx in ALLOWED_SPDX:
        return False
    if spdx == "All-Rights-Reserved":
        return True
    upper = spdx.upper()
    return any(m in upper for m in REJECTED_LICENSE_MARKERS)


def license_reject_message(spdx: str | None) -> str:
    """Kid/ops-facing reject — only unknown, ARR, ND, proprietary."""
    if not spdx:
        return "I couldn't tell the license for that schematic, so I won't add it."
    if spdx == "All-Rights-Reserved":
        return (
            "That build is all-rights-reserved — I can't add it "
            "unless an op uses the friends-server override."
        )
    upper = spdx.upper()
    if "ND" in upper or "NODERIV" in upper:
        return "That license doesn't allow remixing (no-derivatives), so I won't add it."
    if "PROPRIETARY" in upper or "NOASSERTION" in upper:
        return "That schematic's license isn't clear enough to add."
    return f"That license ({spdx}) isn't allowed for this server."


def _decode_varints(raw: bytes, count: int) -> list[int]:
    indices: list[int] = []
    i = 0
    while len(indices) < count and i < len(raw):
        value = 0
        shift = 0
        while True:
            b = raw[i]
            i += 1
            value |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        indices.append(value)
    return indices


def parse_schem_dims(path: Path) -> tuple[list[int], int]:
    """Return ([w,h,l], non_air_count_or_volume) from a Sponge .schem (v2 or v3)."""
    import nbtlib

    nbt = nbtlib.load(path)
    root = nbt["Schematic"] if "Schematic" in nbt else nbt
    w, h, l = int(root["Width"]), int(root["Height"]), int(root["Length"])
    footprint = [w, h, l]
    max_blocks = w * h * l
    try:
        # Sponge v3: Blocks.{Palette,Data} ; v2: Palette + BlockData at root.
        if "Blocks" in root:
            blocks = root["Blocks"]
            palette = {str(k): int(v) for k, v in blocks["Palette"].items()}
            raw = bytes(blocks["Data"])
        else:
            palette = {str(k): int(v) for k, v in root["Palette"].items()}
            raw = bytes(root["BlockData"])
        air_ids = {
            idx
            for name, idx in palette.items()
            if name.split("[", 1)[0] in ("minecraft:air", "air", "minecraft:cave_air", "minecraft:void_air")
        }
        volume = w * h * l
        indices = list(raw) if len(raw) == volume else _decode_varints(raw, volume)
        non_air = sum(1 for idx in indices if idx not in air_ids)
        if non_air > 0:
            max_blocks = non_air
    except Exception:
        pass
    return footprint, max_blocks


def try_convert_litematic(src: Path, dest: Path) -> None:
    """Convert ``.litematic`` → Sponge ``.schem`` in place at ``dest``.

    Raises ``IngestError`` with the real failure reason (never a silent miss).
    """
    converters = [
        ["litematica-cli", "convert", str(src), "-o", str(dest)],
        ["schematic-converter", str(src), str(dest)],
    ]
    cli_errors: list[str] = []
    for cmd in converters:
        if shutil.which(cmd[0]) is None:
            continue
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 0:
            return
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        cli_errors.append(f"{cmd[0]}: {err[:240]}")

    # Shared pipeline converter (litemapy + varint-safe BlockData).
    try:
        from scripts.schem_pipeline.convert import ConvertError, ensure_schem

        ensure_schem(src, dest)
    except ImportError as exc:
        hint = "; ".join(cli_errors) if cli_errors else "no CLI converter on PATH"
        raise IngestError(
            f"litematic → schem needs litemapy (image dep) or a CLI converter.\n"
            f"({hint}; import: {exc})"
        ) from exc
    except ConvertError as exc:
        raise IngestError(f"litematic → schem failed: {exc}") from exc
    except Exception as exc:
        raise IngestError(f"litematic → schem failed: {type(exc).__name__}: {exc}") from exc
    if not dest.is_file() or dest.stat().st_size <= 0:
        raise IngestError(f"litematic → schem produced empty output for {src.name}")


def extract_page_meta(html: str, page_url: str) -> dict[str, Any]:
    meta: dict[str, Any] = {"source_url": page_url}
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if title_m:
        meta["title"] = re.sub(r"<[^>]+>", "", unescape(title_m.group(1))).strip()
    if "title" not in meta:
        og = re.search(r'property="og:title"\s+content="([^"]+)"', html, re.I)
        if og:
            meta["title"] = unescape(og.group(1)).replace(" Schematic", "").strip()

    for key, field in (("Author", "author"), ("License", "license_raw")):
        m = re.search(rf"<dt>\s*{key}\s*</dt>\s*<dd>(.*?)</dd>", html, re.I | re.S)
        if m:
            meta[field] = re.sub(r"<[^>]+>", "", unescape(m.group(1))).strip()

    for m in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        raw = unescape(m.group(1)).strip().replace("&#x2B;", "+")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") in {
            "CreativeWork",
            "SoftwareApplication",
        }:
            if data.get("license") and "license_raw" not in meta:
                meta["license_raw"] = str(data["license"])
            if data.get("name") and "title" not in meta:
                meta["title"] = str(data["name"])

    hrefs = re.findall(r'href="([^"]+)"', html, re.I)
    downloads: list[str] = []
    for href in hrefs:
        full = urljoin(page_url, unescape(href))
        low = full.lower()
        if any(low.endswith(ext) for ext in (".schem", ".zip", ".litematic")):
            downloads.append(full)
        elif low.rstrip("/").endswith("/download") or "/download" in low:
            downloads.append(full)
    meta["download_candidates"] = list(dict.fromkeys(downloads))
    return meta


def resolve_shulkr_meta(page_url: str) -> dict[str, Any]:
    m = re.search(r"shulkr\.com/schematics/([A-Za-z0-9]+)", page_url)
    if not m:
        raise IngestError(f"cannot parse Shulkr schematic id from {page_url}")
    sid = m.group(1)
    body, _, _ = http_get(f"https://api.shulkr.com/schematics/{sid}")
    data = json.loads(body.decode("utf-8"))
    owner = data.get("owner") or {}
    author = owner.get("name") or owner.get("handle") or "unknown"
    dims = data.get("dimensions") or {}
    return {
        "source_url": page_url.split("?")[0],
        "source_id": f"shulkr_{sid}",
        "source_ref": f"shulkr:{sid}",
        "title": data.get("title") or sid,
        "author": author,
        "license_raw": "All-Rights-Reserved",
        "license": "All-Rights-Reserved",
        "attribution": (
            f"{data.get('title', sid)} by {author} — via Shulkr (friends-server curated)"
        ),
        "footprint_hint": (
            [int(dims["x"]), int(dims["y"]), int(dims["z"])]
            if dims.get("x") is not None
            else None
        ),
        "max_blocks_hint": int(data["blockCount"]) if data.get("blockCount") is not None else None,
        "file_id": data.get("fileId") or data.get("primaryFileId"),
        "shulkr_id": sid,
    }


def _license_from_bloxelizer_desc(desc: str) -> str | None:
    """Infer SPDX from Bloxelizer description text (rarely present)."""
    low = (desc or "").lower()
    if "noncommercial" in low or "cc-by-nc" in low or "cc by-nc" in low:
        return "CC-BY-NC-4.0"
    if "cc-by-sa" in low or "creativecommons.org/licenses/by-sa" in low:
        return "CC-BY-SA-4.0"
    if "cc-by" in low or "creativecommons.org/licenses/by/" in low:
        return "CC-BY-4.0"
    if "cc0" in low or "public domain" in low:
        return "CC0-1.0"
    return None


def resolve_bloxelizer_meta(page_url: str) -> dict[str, Any]:
    """Resolve Bloxelizer page → API slug meta (render_token, sizes, license)."""
    m = re.search(r"bloxelizer\.com/schematics/([A-Za-z0-9\-]+)", page_url)
    if not m:
        raise IngestError(f"not a Bloxelizer schematic page: {page_url}")
    slug = m.group(1)
    body, _, _ = http_get(f"{BLOXELIZER_API}/schematics/slug/{slug}")
    data = json.loads(body.decode("utf-8"))
    sid = str(data.get("id") or "")
    if not sid:
        raise IngestError(f"Bloxelizer API returned no id for slug={slug}")
    token = data.get("render_token")
    if not token:
        raise IngestError(f"Bloxelizer API returned no render_token for slug={slug}")
    title = str(data.get("name") or slug)
    author = str(data.get("username") or "") or None
    desc = str(data.get("description") or "")
    lic = _license_from_bloxelizer_desc(desc) or BLOXELIZER_DEFAULT_LICENSE
    source_url = f"https://bloxelizer.com/schematics/{slug}"
    attribution = (
        f"{title} by {author} ({lic}) — via Bloxelizer"
        if author
        else f"{title} ({lic}) — via Bloxelizer"
    )
    sx, sy, sz = data.get("size_x"), data.get("size_y"), data.get("size_z")
    return {
        "source_url": source_url,
        "source_id": f"bloxelizer_{sid}",
        "source_ref": f"bloxelizer:{slug}",
        "title": title,
        "author": author,
        "license_raw": lic,
        "license": lic,
        "attribution": attribution,
        "footprint_hint": (
            [int(sx), int(sy), int(sz)]
            if sx is not None and sy is not None and sz is not None
            else None
        ),
        "max_blocks_hint": (
            int(data["block_count"]) if data.get("block_count") is not None else None
        ),
        "bloxelizer_id": sid,
        "bloxelizer_slug": slug,
        "render_token": str(token),
        "download_hint": "litematic",
    }


def find_asset_in_dir(root: Path) -> Path:
    schems = sorted(root.rglob("*.schem"), key=lambda p: (-p.stat().st_size, len(p.name)))
    if schems:
        return schems[0]
    lites = sorted(root.rglob("*.litematic"), key=lambda p: (-p.stat().st_size, len(p.name)))
    if lites:
        return lites[0]
    raise IngestError(f"no .schem or .litematic found under {root}")


def materialize_schem(source: Path, work: Path) -> Path:
    """Return a path to a .schem file (converting/extracting as needed)."""
    if source.suffix.lower() == ".schem":
        return source
    if source.suffix.lower() == ".zip" or zipfile.is_zipfile(source):
        extract_dir = work / "unzipped"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as zf:
            zf.extractall(extract_dir)
        return materialize_schem(find_asset_in_dir(extract_dir), work)
    if source.suffix.lower() == ".litematic":
        out = work / f"{source.stem}.schem"
        try_convert_litematic(source, out)
        return out
    if source.suffix.lower() == ".shulkr" or source.read_bytes()[:4] == b"SBLD":
        raise IngestError(
            "Shulkr proprietary .shulkr builds are not auto-converted.\n"
            "In the browser: Download schematic → .schem, then:\n"
            "  make ingest-schem URL='/path/to/file.schem' ID=<id> \\\n"
            "    SOURCE_URL='https://www.shulkr.com/schematics/...'"
        )
    head = source.read_bytes()[:2]
    if head == b"PK":
        renamed = work / f"{source.name}.zip"
        shutil.copy2(source, renamed)
        return materialize_schem(renamed, work)
    if head == b"\x1f\x8b":
        dest = work / f"{source.stem}.schem"
        shutil.copy2(source, dest)
        return dest
    raise IngestError(f"unsupported file type: {source.name}")


def _write_download(work: Path, raw: bytes, final_url: str, ctype: str) -> Path:
    fl = final_url.lower().split("?", 1)[0]
    suffix = ".bin"
    if fl.endswith(".schem") or (
        raw[:2] == b"\x1f\x8b" and "zip" not in (ctype or "").lower()
    ):
        suffix = ".schem"
    elif fl.endswith(".zip") or raw[:2] == b"PK" or "zip" in (ctype or "").lower():
        suffix = ".zip"
    elif fl.endswith(".litematic"):
        suffix = ".litematic"
    elif raw[:4] == b"SBLD":
        suffix = ".shulkr"
    asset = work / f"download{suffix}"
    asset.write_bytes(raw)
    return asset


def resolve_download(url: str, work: Path) -> tuple[Path, dict[str, Any]]:
    meta: dict[str, Any] = {"source_url": url}
    parsed = urlparse(url)

    if parsed.scheme in {"", "file"}:
        local = Path(parsed.path) if parsed.scheme == "file" else Path(url).expanduser()
        if not local.is_file():
            local = Path(url).expanduser().resolve()
        if not local.is_file():
            raise IngestError(f"local file not found: {url}")
        meta["source_url"] = str(local.resolve())
        return local.resolve(), meta

    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if (
        "shulkr.com" in host
        and "/schematics/" in path
        and not path.endswith((".schem", ".zip", ".litematic"))
    ):
        meta = resolve_shulkr_meta(url)
        file_id = meta.get("file_id")
        sid = meta.get("shulkr_id")
        if file_id and sid:
            body, _, _ = http_get(
                f"https://api.shulkr.com/schematics/{sid}/files/{file_id}/build-url"
            )
            info = json.loads(body.decode("utf-8"))
            build_url = info.get("url")
            if build_url:
                raw, _, _ = http_get(build_url)
                if raw[:4] == b"SBLD":
                    raise IngestError(
                        "Shulkr page resolved to proprietary .shulkr (browser converts to .schem).\n"
                        "Download .schem from the Shulkr UI, then:\n"
                        f"  make ingest-schem URL='/path/to/{slugify(str(meta.get('title') or sid))}.schem' "
                        f"ID=<catalog_id> SOURCE_URL='{meta['source_url']}'\n"
                        "Tip: pass --allow-arr for friends-server ARR provenance."
                    )
                return _write_download(work, raw, build_url, ""), meta
        raise IngestError(
            "Shulkr page could not yield a .schem. Download .schem in the browser "
            "and ingest that file with SOURCE_URL set to the page."
        )

    if (
        "bloxelizer.com" in host
        and "/schematics/" in path
        and not path.endswith((".schem", ".zip", ".litematic"))
    ):
        # API slug → CDN litematic → materialize_schem converts to Schematic-root .schem.
        meta = resolve_bloxelizer_meta(url)
        sid = meta["bloxelizer_id"]
        token = meta["render_token"]
        cdn = BLOXELIZER_CDN.format(id=sid, token=token)
        raw, dl_final, ctype = http_get(cdn)
        asset = work / f"bloxelizer_{slugify(str(meta.get('bloxelizer_slug') or sid))}.litematic"
        asset.write_bytes(raw)
        meta["download_url"] = dl_final or cdn
        meta["_cdn_ctype"] = ctype
        return asset, meta

    if (
        "schemcraft.com" in host
        and "/schematics/" in path
        and not path.endswith((".schem", ".zip", ".litematic"))
    ):
        html, final_url, _ = http_get(url)
        page_meta = extract_page_meta(html.decode("utf-8", "replace"), final_url)
        meta.update(page_meta)
        dl = re.sub(r"/download/?$", "", final_url.rstrip("/")) + "/download"
        raw, dl_final, ctype = http_get(dl)
        asset = _write_download(work, raw, dl_final, ctype)
        meta["download_url"] = dl_final
        meta["license"] = normalize_license(meta.get("license_raw"))
        if meta.get("author") and meta.get("title"):
            lic = meta.get("license") or meta.get("license_raw") or "unknown license"
            meta["attribution"] = (
                f"{meta['title']} by {meta['author']} ({lic}) — via SchemCraft"
            )
        slug = Path(urlparse(final_url).path.rstrip("/")).name
        meta["source_id"] = f"schemcraft_{slugify(slug)}"
        meta["source_ref"] = f"schemcraft:{slug}"
        return asset, meta

    raw, final_url, ctype = http_get(url)
    low_ctype = (ctype or "").lower()
    if "text/html" in low_ctype or raw.lstrip()[:1] == b"<":
        page_meta = extract_page_meta(raw.decode("utf-8", "replace"), final_url)
        meta.update(page_meta)
        meta["license"] = normalize_license(meta.get("license_raw"))

        def rank(u: str) -> tuple[int, int]:
            lu = u.lower()
            if lu.endswith(".schem"):
                return (0, len(u))
            if lu.endswith(".zip"):
                return (1, len(u))
            if "/download" in lu:
                return (2, len(u))
            if lu.endswith(".litematic"):
                return (3, len(u))
            return (9, len(u))

        candidates = sorted(page_meta.get("download_candidates") or [], key=rank)
        if not candidates:
            raise IngestError(
                f"page has no obvious .schem/.zip download link: {url}\n"
                "Pass a direct file URL or a local .schem path."
            )
        raw, final_url, ctype = http_get(candidates[0])
        meta["download_url"] = final_url

    if "license" not in meta and meta.get("license_raw"):
        meta["license"] = normalize_license(meta.get("license_raw"))
    return _write_download(work, raw, final_url, ctype), meta


def merge_aliases(existing: list[str], extra: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for a in existing + extra:
        key = a.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(a.strip())
    return out


def match_existing_id(title: str, catalog: dict[str, Any]) -> str | None:
    needle = slugify(title)
    templates = catalog.get("templates") or []
    for t in templates:
        if str(t.get("id")) == needle:
            return str(t["id"])
    for t in templates:
        if slugify(str(t.get("title") or "")) == needle:
            return str(t["id"])
    return None


def infer_id(meta: dict[str, Any], url: str) -> str:
    title = meta.get("title")
    if title:
        return slugify(str(title))
    path = urlparse(url).path.rstrip("/")
    name = Path(path).name
    if name and name not in {"download", "schematics"}:
        return slugify(re.sub(r"\.(schem|zip|litematic)$", "", name, flags=re.I))
    return "ingested_schem"


def upsert_catalog(
    *,
    tid: str,
    title: str,
    aliases: list[str],
    footprint: list[int],
    max_blocks: int,
    provenance: dict[str, Any],
    gold: bool,
    dry_run: bool,
) -> dict[str, Any]:
    cat_path = catalog_path()
    catalog = json.loads(cat_path.read_text(encoding="utf-8"))
    templates: list[dict[str, Any]] = list(catalog.get("templates") or [])
    by_id = {str(t.get("id")): t for t in templates}
    existing = by_id.get(tid)
    if existing is None:
        entry: dict[str, Any] = {
            "id": tid,
            "title": title,
            "category": "house",
            "complexity": "common",
            "tags": ["building"],
            "aliases": aliases,
            "schematic": f"{tid}.schem",
            "footprint": footprint,
            "max_blocks": max_blocks,
            "distance_default": 4,
            "follow_up": [],
            "fallback": {
                "tool": "build_house_at_player",
                "args": {
                    "width": max(5, footprint[0] - 2),
                    "depth": max(5, footprint[2] - 2),
                    "height": max(4, footprint[1] - 2),
                },
            },
            "deterministic_seed_version": "1",
            "gold": gold,
        }
        templates.append(entry)
        action = "created"
    else:
        entry = existing
        entry["title"] = title or entry.get("title") or tid
        entry["schematic"] = f"{tid}.schem"
        entry["footprint"] = footprint
        entry["max_blocks"] = max_blocks
        entry["gold"] = gold
        entry["aliases"] = merge_aliases(list(entry.get("aliases") or []), aliases)
        action = "updated"

    # Always persist provenance fields used for local attribution.
    for key in ("source_url", "source_id", "source_ref", "license", "author", "attribution"):
        val = provenance.get(key)
        if val is not None and str(val).strip():
            entry[key] = val
    if not entry.get("source_id"):
        entry["source_id"] = f"ingest_{tid}"
    if not entry.get("source_ref"):
        entry["source_ref"] = f"ingest:{tid}"

    catalog["templates"] = sorted(templates, key=lambda t: str(t.get("id") or ""))
    if not dry_run:
        cat_path.write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    entry["_action"] = action
    return entry


def enrich_from_source_url(meta: dict[str, Any], source_url: str) -> None:
    meta["source_url"] = source_url
    if "shulkr.com" in source_url:
        meta.update(
            {
                k: v
                for k, v in resolve_shulkr_meta(source_url).items()
                if k not in {"footprint_hint", "max_blocks_hint", "file_id", "shulkr_id"}
            }
        )
    elif "bloxelizer.com" in source_url:
        meta.update(
            {
                k: v
                for k, v in resolve_bloxelizer_meta(source_url).items()
                if k
                not in {
                    "footprint_hint",
                    "max_blocks_hint",
                    "bloxelizer_id",
                    "bloxelizer_slug",
                    "render_token",
                    "download_hint",
                }
            }
        )
    elif "schemcraft.com" in source_url:
        html, final, _ = http_get(source_url)
        page_meta = extract_page_meta(html.decode("utf-8", "replace"), final)
        meta.update(page_meta)
        meta["license"] = normalize_license(meta.get("license_raw"))
        slug = Path(urlparse(final).path.rstrip("/")).name
        meta.setdefault("source_id", f"schemcraft_{slugify(slug)}")
        meta.setdefault("source_ref", f"schemcraft:{slug}")


@dataclass
class IngestResult:
    ok: bool
    template_id: str = ""
    title: str = ""
    gold: bool = False
    footprint: list[int] | None = None
    max_blocks: int = 0
    license: str | None = None
    author: str | None = None
    source_url: str = ""
    aliases: list[str] | None = None
    action: str = ""
    error: str = ""
    schem_path: str = ""


def url_allowlisted(url: str) -> tuple[bool, str]:
    """Return (ok, reason). SchemCraft / Bloxelizer / Shulkr + direct .schem/.zip OK."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme in {"", "file"}:
        local = Path(parsed.path if parsed.scheme == "file" else url).expanduser()
        if local.is_file() and local.suffix.lower() in {".schem", ".zip", ".litematic"}:
            return True, "local file"
        return False, "local path must be an existing .schem/.zip/.litematic"
    if parsed.scheme not in {"http", "https"}:
        return False, "only http(s) or local files"
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if host in ALLOWLIST_HOSTS:
        return True, f"allowlisted host:{host}"
    if path.endswith((".schem", ".zip")):
        return True, "direct schematic/zip URL"
    return False, (
        "URL not on allowlist. Use schemcraft.com, bloxelizer.com, shulkr.com, "
        "or a direct .schem/.zip link."
    )


def ingest_url(
    url: str,
    *,
    template_id: str | None = None,
    title: str | None = None,
    source_url: str | None = None,
    author: str | None = None,
    license: str | None = None,
    allow_arr: bool = False,
    allow_rejected_license: bool = False,
    gold: bool = True,
    dry_run: bool = False,
    require_allowlist: bool = False,
) -> IngestResult:
    """In-process ingest used by CLI and ops `/ai ingest` route."""
    if require_allowlist:
        ok, reason = url_allowlisted(url)
        if not ok:
            return IngestResult(ok=False, error=reason, source_url=url)

    # Auto-allow ARR for Shulkr friends-curated megas when host matches.
    host = (urlparse(url).netloc or "").lower()
    if "shulkr.com" in host:
        allow_arr = True

    out_dir = schem_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ingest_schem_") as tmp:
        work = Path(tmp)
        try:
            asset, meta = resolve_download(url, work)
            if source_url:
                try:
                    enrich_from_source_url(meta, source_url)
                except Exception as exc:
                    meta["source_url"] = source_url
                    meta.setdefault("_enrich_error", str(exc))
            schem_src = materialize_schem(asset, work)
            footprint, max_blocks = parse_schem_dims(schem_src)
        except IngestError as exc:
            return IngestResult(ok=False, error=str(exc), source_url=url)
        except Exception as exc:
            return IngestResult(ok=False, error=f"ingest failed: {exc}", source_url=url)

        cat_path = catalog_path()
        catalog = json.loads(cat_path.read_text(encoding="utf-8"))
        if template_id:
            tid = slugify(template_id)
        else:
            guess_title = title or meta.get("title") or "Ingested schematic"
            tid = match_existing_id(str(guess_title), catalog) or infer_id(meta, url)
        existing = next(
            (t for t in (catalog.get("templates") or []) if t.get("id") == tid),
            None,
        )
        resolved_title = (
            title
            or (existing.get("title") if existing else None)
            or meta.get("title")
            or tid
        )
        license_spdx = (
            license
            or meta.get("license")
            or normalize_license(meta.get("license_raw"))
            or (existing.get("license") if existing else None)
        )
        if license_rejected(license_spdx):
            if license_spdx == "All-Rights-Reserved" and allow_arr:
                pass
            elif allow_rejected_license:
                pass
            else:
                return IngestResult(
                    ok=False,
                    error=license_reject_message(license_spdx),
                    source_url=str(meta.get("source_url") or url),
                    template_id=tid,
                    title=str(resolved_title),
                    license=license_spdx,
                )

        source_page = (
            meta.get("source_url")
            or (existing.get("source_url") if existing else None)
            or url
        )
        author_name = (
            author
            or meta.get("author")
            or (existing.get("author") if existing else None)
            or "Unknown"
        )
        attribution = meta.get("attribution") or (
            existing.get("attribution") if existing else None
        )
        if not attribution:
            attribution = f"{resolved_title} by {author_name}"
            if license_spdx:
                attribution += f" ({license_spdx})"
            if source_page:
                attribution += f" — {source_page}"
        provenance = {
            "source_url": source_page,
            "source_id": meta.get("source_id")
            or (existing.get("source_id") if existing else None),
            "source_ref": meta.get("source_ref")
            or (existing.get("source_ref") if existing else None),
            "license": license_spdx,
            "author": author_name,
            "attribution": attribution,
        }
        missing_prov = [
            k
            for k in ("source_url", "license", "author", "attribution")
            if not provenance.get(k)
        ]
        if missing_prov:
            return IngestResult(
                ok=False,
                error=(
                    "Missing provenance "
                    f"({', '.join(missing_prov)}) — need source link + license "
                    "for attribution."
                ),
                source_url=str(source_page or url),
                template_id=tid,
                title=str(resolved_title),
                license=license_spdx,
                author=author_name,
            )
        new_aliases = merge_aliases(
            aliases_from_title(str(resolved_title)),
            EXTRA_ALIASES.get(tid, []),
        )
        dest = out_dir / f"{tid}.schem"
        if not dry_run:
            backup_seed_schem(dest)
            shutil.copy2(schem_src, dest)
        entry = upsert_catalog(
            tid=tid,
            title=str(resolved_title),
            aliases=new_aliases,
            footprint=footprint,
            max_blocks=max_blocks,
            provenance=provenance,
            gold=gold,
            dry_run=dry_run,
        )

    return IngestResult(
        ok=True,
        template_id=tid,
        title=str(entry.get("title") or resolved_title),
        gold=bool(entry.get("gold")),
        footprint=list(footprint),
        max_blocks=int(max_blocks),
        license=provenance.get("license"),
        author=provenance.get("author"),
        source_url=str(provenance.get("source_url") or url),
        aliases=list(entry.get("aliases") or new_aliases),
        action=str(entry.get("_action") or ""),
        schem_path=str(dest),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        required=True,
        help="page URL, direct file URL, or local .schem path",
    )
    parser.add_argument("--id", help="catalog template id (e.g. house_cottage_small)")
    parser.add_argument("--title", help="override catalog title")
    parser.add_argument(
        "--source-url",
        dest="source_url_override",
        help="provenance page URL when --url is a local/direct file",
    )
    parser.add_argument("--author", help="override author")
    parser.add_argument("--license", help="override SPDX license")
    parser.add_argument(
        "--allow-arr",
        action="store_true",
        help="allow All-Rights-Reserved (friends curated Shulkr)",
    )
    parser.add_argument(
        "--allow-rejected-license",
        action="store_true",
        help="allow ND/unknown rejected licenses (not recommended)",
    )
    parser.add_argument("--dry-run", action="store_true", help="resolve + print; do not write")
    parser.add_argument(
        "--no-gold",
        action="store_true",
        help="write schem + catalog fields but leave gold:false",
    )
    args = parser.parse_args(argv)

    result = ingest_url(
        args.url,
        template_id=args.id,
        title=args.title,
        source_url=args.source_url_override,
        author=args.author,
        license=args.license,
        allow_arr=args.allow_arr,
        allow_rejected_license=args.allow_rejected_license,
        gold=not args.no_gold,
        dry_run=args.dry_run,
    )
    if not result.ok:
        print(f"error: {result.error}", file=sys.stderr)
        err = (result.error or "").lower()
        if "license" in err or "all-rights-reserved" in err or "provenance" in err:
            return 2
        return 1

    fp = result.footprint or [0, 0, 0]
    phrases = result.aliases or []
    print(f"id:        {result.template_id}")
    print(f"title:     {result.title}")
    print(f"gold:      {result.gold}")
    print(f"schematic: agent/templates/schematics/{result.template_id}.schem")
    print(f"footprint: {fp[0]}x{fp[1]}x{fp[2]}  max_blocks={result.max_blocks}")
    print(f"license:   {result.license}")
    print(f"author:    {result.author}")
    print(f"source:    {result.source_url}")
    print(f"action:    {result.action}")
    print("phrases:")
    for p in phrases[:12]:
        print(f"  - {p}")
    if len(phrases) > 12:
        print(f"  … +{len(phrases) - 12} more")
    print()
    print("next: make companion-reload")
    print("      # restarts mc-agent only (catalog + ranker reload)")
    print("      # then live-test as firecrab93: /agent build me a …")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
