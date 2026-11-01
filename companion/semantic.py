"""Local bag-of-words embeddings for companion template ranking.

CPU-only, no GPU / external vector DB. Mirrors ``agent/templates/embedding_backend.py``
so the live ``/agent`` paste path can use the same hybrid semantics without shipping
the full agent package into ``mc-agent``.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import threading
from dataclasses import dataclass

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "in",
        "on",
        "at",
        "by",
        "to",
        "for",
        "is",
        "are",
        "be",
        "with",
        "me",
        "my",
        "i",
        "you",
        "we",
        "us",
        "it",
        "this",
        "that",
        "build",
        "make",
        "place",
        "put",
        "give",
        "want",
        "need",
        "please",
        "can",
        "could",
        "would",
        "small",
        "big",
        "large",
        "tiny",
        "near",
        "here",
        "there",
        "nearby",
    }
)

_TOKEN_RX = re.compile(r"[a-z0-9]+")

# Common kid typos → canonical token (applied before stemming).
_TYPO_MAP = {
    "markket": "market",
    "markett": "market",
    "maket": "market",
    "marcket": "market",
    "marketstal": "marketstall",
    "ignloo": "igloo",
    "iglo": "igloo",
    "chiken": "chicken",
    "chickn": "chicken",
    "castel": "castle",
    "bridg": "bridge",
    "biridge": "bridge",
    "greenhous": "greenhouse",
    "greenhause": "greenhouse",
    "lightouse": "lighthouse",
    "lighthosue": "lighthouse",
    "watchtowr": "watchtower",
    "cottge": "cottage",
    "cotage": "cottage",
    # campground near-misses (transpositions / dropped letters)
    "cmapground": "campground",
    "camground": "campground",
    "campgorund": "campground",
    "campgrond": "campground",
    "campgound": "campground",
    "campgrund": "campground",
    "campgroud": "campground",
    "campingground": "campground",
}

# Long structure tokens used for bounded edit-distance recovery when a kid
# mistypes a single jammed word (e.g. cmapground → campground). Keep this
# list specific so soft matching cannot invent crop/farm steals.
_NEAR_LEXICON = frozenset(
    {
        "campground",
        "playground",
        "greenhouse",
        "lighthouse",
        "watchtower",
        "blacksmith",
        "marketstall",
        "sugarcane",
        "windmill",
        "apartment",
        "cathedral",
    }
)

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
    "stall": "stall",
    "stalls": "stall",
    "stand": "stall",
    "stands": "stall",
    "booth": "stall",
    "booths": "stall",
    "vendor": "market",
    "vendors": "market",
    "market": "market",
    "markets": "market",
    "trees": "tree",
    "farms": "farm",
    "barns": "barn",
    "towers": "tower",
    "watchtower": "tower",
    "lighthouses": "lighthouse",
    "gazebos": "gazebo",
    "huts": "hut",
    "cabins": "cabin",
    "fowl": "chicken",
    "poultry": "chicken",
    "livestock": "animal",
    "stable": "stable",
    "stables": "stable",
    "playground": "playground",
    "kids": "play",
    "children": "play",
    "forest": "tree",
    "woods": "tree",
}

_CATEGORY_KEYWORDS = {
    "farm": "farm animal place pen garden crop plant",
    "house": "house home cottage cabin building dwelling",
    "fortress": "fortress castle defense stone keep tower",
    "infrastructure": "bridge path road market stall shop vendor booth stand pier dock",
    "decoration": "decor village ornament park plaza fountain",
    "utility": "workshop utility building storage smelter",
    "nature_terrain": "tree nature plant",
}


def backend_enabled() -> bool:
    return os.environ.get("TEMPLATE_EMBEDDING_BACKEND", "local").strip().lower() != "disabled"


def ranker_mode() -> str:
    return os.environ.get("TEMPLATE_RANKER_MODE", "hybrid").strip().lower()


def _stem(tok: str) -> str:
    if tok in _TYPO_MAP:
        tok = _TYPO_MAP[tok]
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


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for raw in _TOKEN_RX.findall(text.lower()):
        if raw in _STOPWORDS or len(raw) <= 1:
            continue
        out.append(_stem(raw))
    return out


def _edit_distance(a: str, b: str, *, limit: int = 2) -> int:
    """Levenshtein with early exit when distance exceeds ``limit``."""

    if a == b:
        return 0
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            val = min(ins, delete, sub)
            cur.append(val)
            row_min = min(row_min, val)
        if row_min > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _near_lexicon_fix(token: str) -> str | None:
    """Map a long unknown token onto a unique near lexicon entry, else None."""

    if len(token) < 7 or token in _NEAR_LEXICON or token in _TYPO_MAP:
        return None
    # Already a known stem/synonym — leave alone.
    if token in _SYNONYMS or _stem(token) in _NEAR_LEXICON:
        return None
    best: str | None = None
    best_dist = 99
    second = 99
    for cand in _NEAR_LEXICON:
        # Length gate keeps "cmapground"→campground and rejects short noise.
        if abs(len(token) - len(cand)) > 2:
            continue
        dist = _edit_distance(token, cand, limit=2)
        if dist < best_dist:
            second = best_dist
            best_dist = dist
            best = cand
        elif dist < second:
            second = dist
    # Accept only a clear unique single-edit winner. (2-edit soft matches
    # are too aggressive — e.g. treehouse ↛ greenhouse.)
    if best is not None and best_dist == 1 and second > 1:
        return best
    return None


def correct_typos(text: str) -> str:
    """Return prompt with known typo tokens rewritten (keeps original spacing style)."""

    parts: list[str] = []
    last = 0
    for match in _TOKEN_RX.finditer(text.lower()):
        parts.append(text[last : match.start()])
        raw = match.group(0)
        fixed = _TYPO_MAP.get(raw, raw)
        if fixed == raw:
            near = _near_lexicon_fix(raw)
            if near is not None:
                fixed = near
        parts.append(fixed)
        last = match.end()
    parts.append(text[last:])
    return "".join(parts)


@dataclass
class SparseVector:
    weights: dict[str, float]

    def cosine(self, other: "SparseVector") -> float:
        if not self.weights or not other.weights:
            return 0.0
        dot = 0.0
        for key, value in self.weights.items():
            dot += value * other.weights.get(key, 0.0)
        na = math.sqrt(sum(v * v for v in self.weights.values()))
        nb = math.sqrt(sum(v * v for v in other.weights.values()))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)


def _tf_vector(tokens: list[str]) -> SparseVector:
    if not tokens:
        return SparseVector({})
    counts: dict[str, float] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0.0) + 1.0
    return SparseVector({k: 1.0 + math.log(v) for k, v in counts.items()})


def document_text(item: dict) -> str:
    tid = str(item.get("id") or "")
    title = str(item.get("title") or "")
    category = str(item.get("category") or "")
    tags = " ".join(str(t) for t in (item.get("tags") or []))
    aliases = " ".join(str(a) for a in (item.get("aliases") or []))
    cat_kw = _CATEGORY_KEYWORDS.get(category, "")
    return " ".join([tid.replace("_", " "), title, category, tags, aliases, cat_kw]).lower()


class LocalEmbeddingIndex:
    """In-memory template vectors; rebuilt when catalog fingerprint changes."""

    def __init__(self) -> None:
        self._vectors: dict[str, SparseVector] = {}
        self._catalog_hash: str = ""
        self._lock = threading.Lock()

    def ensure_built(self, items: list[dict]) -> None:
        raw = "|".join(sorted(str(i.get("id") or "") for i in items))
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:16]
        with self._lock:
            if fingerprint == self._catalog_hash and self._vectors:
                return
            vectors: dict[str, SparseVector] = {}
            for item in items:
                tid = str(item.get("id") or "")
                if not tid:
                    continue
                vectors[tid] = _tf_vector(tokenize(document_text(item)))
            self._vectors = vectors
            self._catalog_hash = fingerprint

    def top_similar(
        self, query: str, template_ids: list[str], top_k: int
    ) -> list[tuple[str, float]]:
        qv = _tf_vector(tokenize(query))
        scored: list[tuple[str, float]] = []
        for tid in template_ids:
            tv = self._vectors.get(tid)
            if tv is None:
                continue
            scored.append((tid, qv.cosine(tv)))
        scored.sort(key=lambda row: (-row[1], row[0]))
        return scored[:top_k]


_index: LocalEmbeddingIndex | None = None
_index_lock = threading.Lock()


def get_index() -> LocalEmbeddingIndex:
    global _index
    with _index_lock:
        if _index is None:
            _index = LocalEmbeddingIndex()
        return _index


def warm_index(items: list[dict]) -> None:
    """Build embedding vectors at process start (idempotent)."""

    if not backend_enabled() or ranker_mode() == "lexical_only":
        return
    get_index().ensure_built(items)
