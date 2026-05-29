"""Local CPU embedding backend for template semantic retrieval.

Uses deterministic bag-of-words vectors (no GPU, no external vector DB).
Suitable for hundreds of templates on MacBook Docker and VPS alike.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.templates.catalog import TemplateMeta

_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "in", "on", "at", "by", "to", "for",
        "is", "are", "be", "with", "me", "my", "i", "you", "we", "us", "it",
        "this", "that", "build", "make", "place", "put", "give", "want", "need",
        "please", "can", "could", "would", "small", "big", "large", "tiny",
    }
)

_TOKEN_RX = re.compile(r"[a-z0-9]+")

_SYNONYMS = {
    "coop": "coop",
    "hen": "chicken",
    "hens": "chicken",
    "chickens": "chicken",
    "cows": "cow",
    "pigs": "pig",
    "sheeps": "sheep",
    "horses": "horse",
    "goats": "goat",
    "bees": "bee",
    "rabbits": "rabbit",
    "ducks": "duck",
    "turkeys": "turkey",
    "fortress": "fortress",
    "keep": "keep",
    "castle": "castle",
    "bridges": "bridge",
    "houses": "house",
    "mansion": "house",
    "manor": "house",
    "estate": "house",
    "cottages": "cottage",
    "homes": "house",
    "home": "house",
    "shop": "shop",
    "shops": "shop",
    "store": "shop",
    "stores": "shop",
    "trees": "tree",
    "farms": "farm",
    "barns": "barn",
    "towers": "tower",
    "watchtower": "tower",
    "watch": "tower",
    "lighthouses": "lighthouse",
    "gazebos": "gazebo",
    "huts": "hut",
    "cabins": "cabin",
    "place": "place",
    "places": "place",
    "spot": "place",
    "area": "place",
    "ducks": "chicken",
    "fowl": "chicken",
    "poultry": "chicken",
    "livestock": "animal",
    "stable": "stable",
    "stables": "stable",
    "play": "play",
    "playing": "play",
    "playground": "playground",
    "kid": "play",
    "kids": "play",
    "children": "play",
    "forest": "tree",
    "woods": "tree",
}


def _stem(tok: str) -> str:
    """Light stemming for plural and gerund forms."""

    if tok in _SYNONYMS:
        return _SYNONYMS[tok]
    if len(tok) > 4:
        if tok.endswith("ies"):
            return tok[:-3] + "y"
        if tok.endswith("es") and not tok.endswith(("ses", "xes", "zes")):
            return tok[:-2]
        if tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
            return tok[:-1]
        if tok.endswith("ing"):
            return tok[:-3]
    return tok


def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    for raw in _TOKEN_RX.findall(text.lower()):
        if raw in _STOPWORDS or len(raw) <= 1:
            continue
        out.append(_stem(raw))
    return out


_CATEGORY_KEYWORDS = {
    "farm": "farm animal place pen",
    "house": "house home place building",
    "fortress": "fortress castle defense stone",
    "infrastructure": "bridge path road",
    "decoration": "decor village ornament",
    "utility": "workshop utility building",
    "nature_terrain": "tree nature plant",
}


def template_document_text(meta: "TemplateMeta") -> str:
    """Canonical text blob embedded for each catalog row."""

    parts = [
        meta.id.replace("_", " "),
        meta.title,
        meta.category,
        " ".join(meta.tags),
        " ".join(meta.aliases),
        _CATEGORY_KEYWORDS.get(meta.category, ""),
    ]
    return " ".join(parts).lower()


@dataclass
class SparseVector:
    """Token -> weight map."""

    weights: dict[str, float]

    def cosine(self, other: "SparseVector") -> float:
        if not self.weights or not other.weights:
            return 0.0
        dot = 0.0
        for k, v in self.weights.items():
            dot += v * other.weights.get(k, 0.0)
        na = math.sqrt(sum(v * v for v in self.weights.values()))
        nb = math.sqrt(sum(v * v for v in other.weights.values()))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)


def _tf_vector(tokens: list[str]) -> SparseVector:
    if not tokens:
        return SparseVector({})
    counts: dict[str, float] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0.0) + 1.0
    # log tf
    weights = {k: 1.0 + math.log(v) for k, v in counts.items()}
    return SparseVector(weights)


class LocalEmbeddingIndex:
    """In-memory template vectors; rebuild on catalog reload."""

    def __init__(self) -> None:
        self._vectors: dict[str, SparseVector] = {}
        self._catalog_hash: str = ""

    def _catalog_fingerprint(self, metas: list["TemplateMeta"]) -> str:
        raw = "|".join(sorted(m.id for m in metas))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def ensure_built(self, metas: list["TemplateMeta"]) -> None:
        fp = self._catalog_fingerprint(metas)
        if fp == self._catalog_hash and self._vectors:
            return
        self._vectors = {}
        for meta in metas:
            doc = template_document_text(meta)
            self._vectors[meta.id] = _tf_vector(_tokenize(doc))
        self._catalog_hash = fp
        cache_dir = Path(
            os.environ.get(
                "TEMPLATE_RANK_INDEX_DIR",
                str(Path(__file__).resolve().parent / ".rank_index"),
            )
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"bow_{fp}.json"
        try:
            payload = {tid: vec.weights for tid, vec in self._vectors.items()}
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass

    def similarity(self, query: str, template_id: str) -> float:
        qv = _tf_vector(_tokenize(query))
        tv = self._vectors.get(template_id)
        if tv is None:
            return 0.0
        return qv.cosine(tv)

    def top_similar(self, query: str, template_ids: list[str], top_k: int) -> list[tuple[str, float]]:
        qv = _tf_vector(_tokenize(query))
        scored: list[tuple[str, float]] = []
        for tid in template_ids:
            tv = self._vectors.get(tid)
            if tv is None:
                continue
            scored.append((tid, qv.cosine(tv)))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:top_k]


_index: LocalEmbeddingIndex | None = None


def get_index() -> LocalEmbeddingIndex:
    global _index
    if _index is None:
        _index = LocalEmbeddingIndex()
    return _index


def backend_enabled() -> bool:
    return os.environ.get("TEMPLATE_EMBEDDING_BACKEND", "local").strip().lower() != "disabled"
