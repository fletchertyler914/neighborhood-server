"""Template catalog: metadata, aliases, schematic paths, safety checks."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

_REPO_ROOT = Path(
    os.environ.get("NEIGHBORHOOD_REPO", Path(__file__).resolve().parents[2])
)
_CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"
_SCHEMATICS_REPO = Path(__file__).resolve().parent / "schematics"
_CONTAINER = os.environ.get("MC_CONTAINER", "mc-lan")
_FAWE_SCHEM_SUBDIR = os.environ.get(
    "AGENT_FAWE_SCHEM_DIR", "plugins/FastAsyncWorldEdit/schematics"
)

# Safe template id: lowercase alnum + underscore only.
_TEMPLATE_ID_RX = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class TemplateMeta:
    id: str
    title: str
    category: str
    tags: tuple[str, ...]
    aliases: tuple[str, ...]
    schematic: str
    footprint: tuple[int, int, int]
    max_blocks: int
    distance_default: int
    follow_up: tuple[dict[str, Any], ...]
    fallback: dict[str, Any] | None
    fallback_steps: tuple[dict[str, Any], ...] = ()
    complexity: str = "basic"
    source_id: str = "neighborhood_internal"
    source_url: str = ""
    source_ref: str = ""
    license: str = "CC-BY-4.0"
    author: str = "neighborhood"
    attribution: str = ""
    content_hash: str = ""
    deterministic_seed_version: str = "1"
    schematics_namespace: str = "neighborhood"

    @property
    def schematic_load_name(self) -> str:
        """FAWE load name: ``namespace/id`` without file extension."""

        base = self.schematic
        if base.endswith(".schem") or base.endswith(".schematic"):
            base = base.rsplit(".", 1)[0]
        return f"{self.schematics_namespace}/{base}"

    def footprint_volume(self) -> int:
        w, h, d = self.footprint
        return max(1, w) * max(1, h) * max(1, d)


_catalog_cache: dict[str, Any] | None = None
_meta_by_id: dict[str, TemplateMeta] | None = None
_alias_to_id: dict[str, str] | None = None
_alias_collisions: list[tuple[str, str, str]] = []


def alias_collisions() -> list[tuple[str, str, str]]:
    """Return (alias, previous_template_id, new_template_id) for duplicate aliases."""

    _build_index()
    return list(_alias_collisions)


def catalog_path() -> Path:
    return _CATALOG_PATH


def schematics_repo_dir() -> Path:
    return _SCHEMATICS_REPO


def _repo_root() -> Path:
    return _REPO_ROOT


def load_catalog() -> dict[str, Any]:
    global _catalog_cache
    if _catalog_cache is None:
        with _CATALOG_PATH.open(encoding="utf-8") as f:
            _catalog_cache = json.load(f)
    return _catalog_cache


def _build_index() -> None:
    global _meta_by_id, _alias_to_id
    if _meta_by_id is not None:
        return
    raw = load_catalog()
    ns = str(raw.get("schematics_namespace") or "neighborhood")
    by_id: dict[str, TemplateMeta] = {}
    aliases: dict[str, str] = {}
    collisions: list[tuple[str, str, str]] = []
    for item in raw.get("templates") or []:
        tid = str(item.get("id") or "").strip()
        if not tid or not _TEMPLATE_ID_RX.match(tid):
            continue
        fp = item.get("footprint") or [7, 5, 7]
        if len(fp) != 3:
            fp = [7, 5, 7]
        fb_steps_raw = item.get("fallback_steps") or []
        meta = TemplateMeta(
            id=tid,
            title=str(item.get("title") or tid),
            category=str(item.get("category") or "general"),
            tags=tuple(str(t) for t in (item.get("tags") or [])),
            aliases=tuple(str(a) for a in (item.get("aliases") or [])),
            schematic=str(item.get("schematic") or f"{tid}.schem"),
            footprint=(int(fp[0]), int(fp[1]), int(fp[2])),
            max_blocks=int(item.get("max_blocks") or 5000),
            distance_default=int(item.get("distance_default") or 3),
            follow_up=tuple(dict(x) for x in (item.get("follow_up") or [])),
            fallback=(
                dict(item["fallback"]) if isinstance(item.get("fallback"), dict) else None
            ),
            fallback_steps=tuple(dict(x) for x in fb_steps_raw if isinstance(x, dict)),
            complexity=str(item.get("complexity") or "basic"),
            source_id=str(item.get("source_id") or "neighborhood_internal"),
            source_url=str(item.get("source_url") or ""),
            source_ref=str(item.get("source_ref") or ""),
            license=str(item.get("license") or "CC-BY-4.0"),
            author=str(item.get("author") or "neighborhood"),
            attribution=str(item.get("attribution") or ""),
            content_hash=str(item.get("content_hash") or ""),
            deterministic_seed_version=str(item.get("deterministic_seed_version") or "1"),
            schematics_namespace=ns,
        )
        _validate_fallback_tools(meta)
        by_id[tid] = meta
        aliases[tid.replace("_", " ")] = tid
        # Also alias the id with trailing size/qualifier word stripped so
        # `sugarcane_farm_small` resolves on a bare "sugarcane farm" input
        # and `house_cottage_small` on "house cottage". This keeps users
        # from having to know the size suffix.
        _STRIP_SUFFIXES = {
            "small", "medium", "large", "big", "tall", "short", "tiny",
            "row", "segment", "plot", "village", "pillar",
        }
        words = tid.split("_")
        if len(words) > 2 and words[-1] in _STRIP_SUFFIXES:
            aliases[" ".join(words[:-1])] = tid
        for alias in meta.aliases:
            key = alias.lower().strip()
            if key:
                prev = aliases.get(key)
                if prev and prev != tid:
                    collisions.append((key, prev, tid))
                aliases[key] = tid
    _meta_by_id = by_id
    _alias_to_id = aliases
    global _alias_collisions
    _alias_collisions = collisions


_KNOWN_FALLBACK_TOOLS: frozenset[str] | None = None


def _validate_fallback_tools(meta: TemplateMeta) -> None:
    global _KNOWN_FALLBACK_TOOLS
    if _KNOWN_FALLBACK_TOOLS is None:
        from agent.tool_registry import TOOL_DEFINITIONS_BY_NAME

        _KNOWN_FALLBACK_TOOLS = frozenset(TOOL_DEFINITIONS_BY_NAME.keys())
    assert _KNOWN_FALLBACK_TOOLS is not None
    if meta.fallback:
        t = str(meta.fallback.get("tool") or "")
        if t and t not in _KNOWN_FALLBACK_TOOLS:
            raise ValueError(f"template {meta.id}: unknown fallback tool {t!r}")
    for step in meta.fallback_steps:
        t = str(step.get("tool") or "")
        if t and t not in _KNOWN_FALLBACK_TOOLS:
            raise ValueError(f"template {meta.id}: unknown fallback_steps tool {t!r}")


def validate_template_id(template_id: str) -> str:
    """Normalize and validate a template id (raises ValueError)."""

    _build_index()
    tid = (template_id or "").strip().lower().replace(" ", "_")
    if not tid:
        raise ValueError("template_id is required")
    if not _TEMPLATE_ID_RX.match(tid):
        raise ValueError(f"invalid template_id: {template_id!r}")
    if tid not in (_meta_by_id or {}):
        raise ValueError(f"unknown template_id: {tid}")
    return tid


def resolve_template_id(text: str) -> str | None:
    """Map prompt fragment or id to canonical template id."""

    _build_index()
    if not text:
        return None
    needle = text.strip().lower()
    if needle in (_meta_by_id or {}):
        return needle
    if needle in (_alias_to_id or {}):
        return _alias_to_id[needle]
    # Longest alias whose text is a *substring* of the needle.
    # E.g. "make me a small chicken coop please" → "chicken coop".
    best_alias_match: tuple[int, str] | None = None
    for alias, tid in (_alias_to_id or {}).items():
        if len(alias) >= 4 and alias in needle:
            if not re.search(rf"(?:^|\W){re.escape(alias)}(?:\W|$)", needle):
                continue
            if best_alias_match is None or len(alias) > best_alias_match[0]:
                best_alias_match = (len(alias), tid)
            elif len(alias) == best_alias_match[0] and tid < best_alias_match[1]:
                best_alias_match = (len(alias), tid)
    if best_alias_match:
        return best_alias_match[1]
    best_score = -1
    best_len = 0
    best_tid: str | None = None
    assert _meta_by_id is not None
    for meta in _meta_by_id.values():
        pool: list[tuple[str, bool]] = [(a, True) for a in meta.aliases]
        pool.extend((t, False) for t in meta.tags)
        for alias, is_explicit in pool:
            al = alias.lower().strip()
            if not al or al not in needle:
                continue
            # Require a real word boundary on at least one side of the
            # match. Avoids "cow pen" landing on `bee_apiary_small` because
            # "p" appeared inside a different alias substring; or "barn"
            # bleeding into `chicken_coop_small` because "arn" appears in
            # "barn" tag of the coop. Single-character substring matches
            # are never enough.
            if len(al) < 3 and not is_explicit:
                continue
            if not re.search(rf"(?:^|\W){re.escape(al)}(?:\W|$)", needle):
                continue
            score = len(al)
            score += 200  # word-boundary bonus
            if is_explicit:
                score += 100
            if " " in al:
                score += 80
            # Penalize tag matches relative to explicit aliases, otherwise
            # short generic tags ("stone", "farm") can outrank a perfectly
            # good multi-word alias on a sibling template.
            if not is_explicit:
                score -= 50
            if score > best_score or (score == best_score and len(al) > best_len):
                best_score = score
                best_len = len(al)
                best_tid = meta.id
    return best_tid


def find_template(template_id: str) -> TemplateMeta:
    tid = validate_template_id(template_id)
    _build_index()
    assert _meta_by_id is not None
    return _meta_by_id[tid]


def iter_templates(
    *,
    category: str | None = None,
    tags: list[str] | None = None,
) -> Iterator[TemplateMeta]:
    _build_index()
    assert _meta_by_id is not None
    tag_set = {t.lower() for t in (tags or [])}
    for meta in _meta_by_id.values():
        if category and meta.category != category:
            continue
        if tag_set and not tag_set.intersection(meta.tags):
            continue
        yield meta


def list_template_summaries(
    *,
    category: str | None = None,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for meta in iter_templates(category=category, tags=tags):
        out.append(
            {
                "id": meta.id,
                "title": meta.title,
                "category": meta.category,
                "tags": list(meta.tags),
                "footprint": list(meta.footprint),
                "has_schematic": schematic_repo_path(meta).is_file(),
                "has_fallback": meta.fallback is not None or bool(meta.fallback_steps),
                "complexity": meta.complexity,
                "source_id": meta.source_id,
            }
        )
    return sorted(out, key=lambda x: x["id"])


def schematic_repo_path(meta: TemplateMeta) -> Path:
    name = meta.schematic
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError("invalid schematic path in catalog")
    return _SCHEMATICS_REPO / name


def server_schematic_path(meta: TemplateMeta) -> Path:
    """Path inside the mc-lan container."""

    return Path("/data") / _FAWE_SCHEM_SUBDIR / meta.schematics_namespace / meta.schematic


def _bind_mounted_schematic_path(meta: TemplateMeta) -> Path:
    """Path to the schematic inside mc-agent's view of the shared data volume.

    The compose stack bind-mounts ``./data`` into both mc-lan (``/data``) and
    mc-agent (``/app/data``). FAWE schematics live under
    ``/data/plugins/FastAsyncWorldEdit/schematics/neighborhood/`` so inside
    mc-agent they're visible at ``/app/data/...``.
    """

    return (
        Path("/app/data")
        / _FAWE_SCHEM_SUBDIR
        / meta.schematics_namespace
        / meta.schematic
    )


def schematic_available_on_server(meta: TemplateMeta) -> bool:
    """True if the schematic file exists in the running mc-lan container."""

    bind_path = _bind_mounted_schematic_path(meta)
    if bind_path.is_file():
        return True

    remote = server_schematic_path(meta)
    try:
        out = subprocess.run(
            ["docker", "exec", _CONTAINER, "test", "-f", str(remote)],
            capture_output=True,
            timeout=10,
        )
        return out.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_schematic_on_server(meta: TemplateMeta) -> bool:
    """Copy repo schematic into FAWE folder if missing. Returns True if present."""

    if schematic_available_on_server(meta):
        return True
    local = schematic_repo_path(meta)
    if not local.is_file():
        return False
    bind_path = _bind_mounted_schematic_path(meta)
    if bind_path.parent.exists() or bind_path.parent.parent.exists():
        try:
            bind_path.parent.mkdir(parents=True, exist_ok=True)
            bind_path.write_bytes(local.read_bytes())
            return schematic_available_on_server(meta)
        except OSError:
            pass
    remote = server_schematic_path(meta)
    remote_dir = str(remote.parent)
    try:
        subprocess.run(
            ["docker", "exec", _CONTAINER, "mkdir", "-p", remote_dir],
            check=True,
            capture_output=True,
            timeout=15,
        )
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                _CONTAINER,
                "sh",
                "-c",
                f"cat > {remote}",
            ],
            input=local.read_bytes(),
            check=True,
            capture_output=True,
            timeout=60,
        )
        return True
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return schematic_available_on_server(meta)


def infer_template_from_prompt(prompt: str, *, intent_family: str = "") -> str | None:
    """Best-effort template id from natural language (hybrid ranker)."""

    from agent.templates.ranking import infer_best_template_id

    _build_index()
    p = (prompt or "").strip()
    if not p:
        return None
    m = re.search(r"template[:\s]+([a-z][a-z0-9_]+)", p, re.I)
    if m:
        tid = resolve_template_id(m.group(1))
        if tid:
            return tid
    ranked = infer_best_template_id(p, intent_family=intent_family)
    if ranked:
        return ranked
    return resolve_template_id(p.lower())


def normalize_template_id(template_id: str) -> str:
    tid = (template_id or "").strip().lower().replace(" ", "_")
    if not tid or not _TEMPLATE_ID_RX.match(tid):
        raise ValueError(f"invalid template_id: {template_id!r}")
    return tid


def register_template_entry(
    template_id: str,
    *,
    title: str | None = None,
    category: str = "community",
    tags: list[str] | None = None,
    schematic: str | None = None,
    footprint: list[int] | None = None,
    overwrite: bool = False,
) -> TemplateMeta:
    """Append or replace a template row in catalog.json (git-curated + in-game publish)."""

    tid = normalize_template_id(template_id)
    _build_index()
    assert _meta_by_id is not None
    if tid in _meta_by_id and not overwrite:
        raise FileExistsError(f"template {tid} already exists")

    raw = load_catalog()
    templates: list[dict[str, Any]] = list(raw.get("templates") or [])
    templates = [t for t in templates if str(t.get("id")) != tid]
    fp = footprint or [7, 5, 7]
    entry = {
        "id": tid,
        "title": title or tid.replace("_", " ").title(),
        "category": category,
        "tags": tags or [],
        "schematic": schematic or f"{tid}.schem",
        "footprint": fp,
        "max_blocks": max(500, fp[0] * fp[1] * fp[2]),
        "distance_default": 3,
        "follow_up": [],
        "fallback": None,
    }
    templates.append(entry)
    raw["templates"] = templates
    with _CATALOG_PATH.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)
        f.write("\n")
    reload_catalog()
    return find_template(tid)


def reload_catalog() -> None:
    """Clear caches (tests)."""

    global _catalog_cache, _meta_by_id, _alias_to_id
    _catalog_cache = None
    _meta_by_id = None
    _alias_to_id = None
