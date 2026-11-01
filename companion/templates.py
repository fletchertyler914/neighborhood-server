"""Curated template matching for the live ``/agent`` paste path.

Hybrid lexical + bag-of-words semantic ranking (see ``companion/semantic.py``).
Strong exact/phrase aliases still win immediately; weak or ambiguous matches
clarify with top kid-friendly options instead of pasting a default house.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from companion.semantic import (
    backend_enabled,
    correct_typos,
    get_index,
    ranker_mode,
    tokenize,
    warm_index,
)

_STOP = {
    "a",
    "an",
    "and",
    "at",
    "build",
    "create",
    "for",
    "here",
    "in",
    "make",
    "me",
    "my",
    "of",
    "place",
    "please",
    "put",
    "some",
    "the",
    "this",
}

# Bare words that many houses share — only win when the ask is essentially
# just that word (+ size adjectives). Never beat "home for my chickens".
_VAGUE_ALIASES = frozenset({"house", "home", "building", "structure"})
_DEFAULT_HOUSE_IDS = frozenset(
    {"house_cottage_small", "cottage_medium", "cabin_log", "modern_house_flat"}
)
_SIZE_WORDS = frozenset(
    {"little", "small", "tiny", "big", "large", "nice", "cozy", "pretty", "starter"}
)
_LARGE_WORDS = frozenset({"large", "big", "huge", "giant", "massive"})
_SMALL_WORDS = frozenset({"little", "small", "tiny", "starter", "mini"})
_PLANT_WORDS = frozenset(
    {
        "garden",
        "farm",
        "greenhouse",
        "crop",
        "plant",
        "flower",
        "herb",
        "orchard",
        "allotment",
        "veggie",
        "vegetable",
        "wheat",
        "carrot",
        "potato",
        "pumpkin",
        "melon",
        "berry",
        "farmland",
        "cane",
        "sugarcane",
    }
)
_MARKET_WORDS = frozenset(
    {
        "market",
        "stall",
        "shop",
        "store",
        "vendor",
        "booth",
        "stand",
        "bakery",
        "blacksmith",
    }
)
_FORT_WORDS = frozenset(
    {"castle", "fort", "fortress", "keep", "tower", "watchtower", "gatehouse"}
)
_BRIDGE_WORDS = frozenset({"bridge", "pier", "dock", "moat"})
_CAMP_WORDS = frozenset(
    {"camp", "camping", "campground", "campsite", "tent", "tents", "campfire"}
)
_CROP_FARM_MARKERS = frozenset(
    {
        "carrot",
        "potato",
        "wheat",
        "pumpkin",
        "melon",
        "berry",
        "sugarcane",
        "crop",
        "farmland",
    }
)


@dataclass(frozen=True)
class TemplateMatch:
    template_id: str
    title: str
    score: float
    matched_alias: str
    gold: bool = False
    confidence: str = "high"
    alternatives: tuple[str, ...] = ()
    needs_clarify: bool = False
    ranking: dict = field(default_factory=dict)


def _stem(token: str) -> str:
    # Light plural fold so "chickens" matches alias "chicken".
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(text: str) -> set[str]:
    return {
        _stem(token)
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _STOP and _stem(token) not in _STOP
    }


@lru_cache(maxsize=1)
def _catalog() -> list[dict]:
    configured = os.environ.get("COMPANION_TEMPLATE_CATALOG")
    candidates = [
        Path(configured) if configured else None,
        Path("/app/assets/catalog.json"),
        Path(__file__).resolve().parents[1] / "agent/templates/catalog.json",
    ]
    for path in candidates:
        if path is not None and path.exists():
            return list(json.loads(path.read_text()).get("templates", []))
    return []


def reload_catalog() -> None:
    _catalog.cache_clear()


def warm_template_ranker() -> None:
    """Pre-build embedding vectors for the live catalog (startup)."""

    warm_index(_catalog())


def is_gold_template(template_id: str) -> bool:
    for item in _catalog():
        if str(item.get("id")) == template_id:
            return bool(item.get("gold"))
    return False


def _footprint_area(item: dict) -> int:
    fp = item.get("footprint") or [7, 5, 7]
    try:
        return max(1, int(fp[0])) * max(1, int(fp[2]))
    except (TypeError, ValueError, IndexError):
        return 49


def _size_prior(prompt_tokens: set[str], item: dict) -> float:
    area = _footprint_area(item)
    if prompt_tokens & _LARGE_WORDS:
        if area >= 100:
            return 0.08
        if area <= 64:
            return -0.04
    if prompt_tokens & _SMALL_WORDS:
        if area <= 81:
            return 0.05
        if area >= 121:
            return -0.04
    return 0.0


def _category_prior(prompt_tokens: set[str], item: dict) -> float:
    cat = str(item.get("category") or "").lower()
    tags = {_stem(str(t).lower()) for t in (item.get("tags") or [])}
    tid = str(item.get("id") or "")
    boost = 0.0

    if prompt_tokens & _PLANT_WORDS:
        if cat == "farm" or tags & {"garden", "crop", "plant", "farm"}:
            boost += 0.12
        if tid == "garden_plot" and "garden" in prompt_tokens:
            boost += 0.15
        if tid == "wheat_farm_small" and "farm" in prompt_tokens and "garden" not in prompt_tokens:
            boost += 0.12
        if tid == "greenhouse_small" and "greenhouse" in prompt_tokens:
            boost += 0.08
        if tid in {"plaza_stone", "road_segment", "bench_row"} or (
            cat == "decoration" and not (tags & {"garden", "plant", "moss"})
        ):
            boost -= 0.1

    if prompt_tokens & _MARKET_WORDS:
        if tid == "market_stall" or tags & {"market", "stall", "shop", "vendor"}:
            boost += 0.22
        if cat in {"infrastructure", "utility"} and tags & {"shop", "market", "stall"}:
            boost += 0.08
        # Default cottages must not steal stall/shop asks.
        if tid in _DEFAULT_HOUSE_IDS or (
            cat == "house" and not (tags & {"market", "stall", "shop", "vendor", "bakery"})
        ):
            boost -= 0.18

    if prompt_tokens & _FORT_WORDS:
        if cat == "fortress" or tags & {"castle", "fort", "tower", "defense"}:
            boost += 0.1
        if tid in _DEFAULT_HOUSE_IDS:
            boost -= 0.08

    if prompt_tokens & _BRIDGE_WORDS:
        if "bridge" in tid or tags & {"bridge", "pier", "dock"}:
            boost += 0.12
        if tid in _DEFAULT_HOUSE_IDS:
            boost -= 0.12

    # Camping ≠ crops: never let a campground typo/semantic ghost boost farms.
    if prompt_tokens & _CAMP_WORDS:
        if tid in {"campground", "tent_camp"} or "camp" in tid:
            boost += 0.22
        if cat == "farm" and (
            tags & {"crop", "plants", "garden"}
            or any(marker in tid for marker in ("farm_small", "farm_dark", "_farm"))
        ):
            boost -= 0.3
        if tid in _DEFAULT_HOUSE_IDS:
            boost -= 0.08

    return boost


def _is_crop_farm(item: dict) -> bool:
    tid = str(item.get("id") or "")
    tags = {_stem(str(t).lower()) for t in (item.get("tags") or [])}
    cat = str(item.get("category") or "").lower()
    if cat != "farm":
        return False
    if tags & {"crop", "plants", "garden"}:
        return True
    return any(marker in tid for marker in _CROP_FARM_MARKERS)


def _confidence_thresholds() -> tuple[float, float, float]:
    high = float(os.environ.get("TEMPLATE_CONFIDENCE_HIGH", "0.72"))
    medium = float(os.environ.get("TEMPLATE_CONFIDENCE_MEDIUM", "0.45"))
    margin = float(os.environ.get("TEMPLATE_RANK_MARGIN", "0.12"))
    return high, medium, margin


def _weights() -> tuple[float, float, float]:
    return (
        float(os.environ.get("TEMPLATE_RANK_W_LEX", "0.55")),
        float(os.environ.get("TEMPLATE_RANK_W_SEM", "0.30")),
        float(os.environ.get("TEMPLATE_RANK_W_POL", "0.15")),
    )


def _top_k() -> int:
    return max(3, min(int(os.environ.get("TEMPLATE_RANK_TOP_K", "8")), 20))


def _lexical_scores(prompt: str, items: list[dict]) -> dict[str, tuple[float, str]]:
    """Per-template best lexical score + matched alias (0..~2 for phrase hits)."""

    normalized = " ".join(re.findall(r"[a-z0-9]+", prompt.lower()))
    prompt_tokens = _tokens(prompt)
    out: dict[str, tuple[float, str]] = {}
    if not prompt_tokens:
        return out
    for item in items:
        aliases = [
            str(item.get("id", "")).replace("_", " "),
            str(item.get("title", "")),
            *[str(alias) for alias in item.get("aliases", [])],
        ]
        best_score = 0.0
        best_alias = ""
        for alias in aliases:
            alias_normalized = " ".join(re.findall(r"[a-z0-9]+", alias.lower()))
            alias_tokens = _tokens(alias)
            if not alias_tokens:
                continue
            if alias_normalized and re.search(
                rf"(?:^|\s){re.escape(alias_normalized)}(?:\s|$)",
                normalized,
            ):
                if (
                    alias_normalized in _VAGUE_ALIASES
                    and alias_tokens <= _VAGUE_ALIASES
                    and (prompt_tokens - _SIZE_WORDS - _VAGUE_ALIASES)
                ):
                    score = 0.35
                else:
                    score = 1.0 + len(alias_tokens) / max(len(prompt_tokens), 1)
            elif alias_tokens and alias_tokens <= prompt_tokens:
                score = 0.9 + 0.05 * min(len(alias_tokens), 4)
                if len(alias_tokens) >= 2:
                    score += 0.08
            else:
                overlap = len(prompt_tokens & alias_tokens)
                score = overlap / len(prompt_tokens | alias_tokens)
            if score > best_score:
                best_score = score
                best_alias = alias
        if best_score > 0:
            best_score += _size_prior(prompt_tokens, item)
            best_score += _category_prior(prompt_tokens, item)
            out[str(item["id"])] = (best_score, best_alias)
    return out


def _normalize_lex(raw: float) -> float:
    """Map legacy lexical scores (often >1 for phrase hits) into 0..1 for fusion."""

    if raw >= 1.0:
        return min(1.0, 0.85 + 0.1 * min(raw - 1.0, 1.5))
    return max(0.0, min(1.0, raw))


def _kid_titles(items_by_id: dict[str, dict], template_ids: list[str]) -> tuple[str, ...]:
    titles: list[str] = []
    for tid in template_ids:
        item = items_by_id.get(tid) or {}
        title = str(item.get("title") or tid.replace("_", " "))
        if title and title not in titles:
            titles.append(title)
    return tuple(titles[:3])


def _match_lexical_only(prompt: str, *, gold_only: bool) -> TemplateMatch | None:
    """Legacy lexical path (also used when embeddings disabled)."""

    items = _catalog()
    lex = _lexical_scores(prompt, items)
    ranked: list[TemplateMatch] = []
    for item in items:
        tid = str(item["id"])
        gold = bool(item.get("gold"))
        if gold_only and not gold:
            continue
        pair = lex.get(tid)
        if not pair:
            continue
        score, alias = pair
        ranked.append(
            TemplateMatch(
                template_id=tid,
                title=str(item.get("title", tid)),
                score=score,
                matched_alias=alias,
                gold=gold,
                confidence="high" if score >= 0.72 else "medium",
            )
        )
    ranked.sort(key=lambda match: (-match.score, match.template_id))
    if not ranked:
        if gold_only:
            non_gold = _match_lexical_only(prompt, gold_only=False)
            if non_gold is not None and not non_gold.gold:
                return non_gold
        return None
    winner = ranked[0]
    runner_up = ranked[1].score if len(ranked) > 1 else 0.0
    alts = tuple(m.title for m in ranked[1:4])
    if winner.score < 0.72 or winner.score - runner_up < 0.12:
        if winner.score >= 0.45:
            return TemplateMatch(
                template_id=winner.template_id,
                title=winner.title,
                score=winner.score,
                matched_alias=winner.matched_alias,
                gold=winner.gold,
                confidence="medium",
                alternatives=alts,
                needs_clarify=True,
            )
        return None
    if gold_only and winner.gold:
        non_gold = _match_lexical_only(prompt, gold_only=False)
        if (
            non_gold is not None
            and not non_gold.gold
            and non_gold.score > winner.score
            and not non_gold.needs_clarify
        ):
            return TemplateMatch(
                template_id=non_gold.template_id,
                title=non_gold.title,
                score=non_gold.score,
                matched_alias=non_gold.matched_alias,
                gold=False,
                confidence=non_gold.confidence,
                alternatives=non_gold.alternatives,
                needs_clarify=True,
            )
    # Default houses need a clear ask — never auto-paste on weak margin.
    if winner.template_id in _DEFAULT_HOUSE_IDS and winner.score < 1.0:
        if winner.score - runner_up < 0.2:
            return TemplateMatch(
                template_id=winner.template_id,
                title=winner.title,
                score=winner.score,
                matched_alias=winner.matched_alias,
                gold=winner.gold,
                confidence="medium",
                alternatives=alts,
                needs_clarify=True,
            )
    return winner


def _exact_alias_hits(prompt: str, items: list[dict]) -> list[tuple[float, str, str, bool]]:
    """Cheap whole-phrase alias scan (no full Jaccard pass)."""

    normalized = " ".join(re.findall(r"[a-z0-9]+", prompt.lower()))
    prompt_tokens = _tokens(prompt)
    if not normalized or not prompt_tokens:
        return []
    hits: list[tuple[float, str, str, bool]] = []
    for item in items:
        tid = str(item.get("id") or "")
        gold = bool(item.get("gold"))
        aliases = [
            tid.replace("_", " "),
            str(item.get("title") or ""),
            *[str(alias) for alias in item.get("aliases", [])],
        ]
        best = 0.0
        best_alias = ""
        for alias in aliases:
            alias_normalized = " ".join(re.findall(r"[a-z0-9]+", alias.lower()))
            if not alias_normalized:
                continue
            if not re.search(
                rf"(?:^|\s){re.escape(alias_normalized)}(?:\s|$)",
                normalized,
            ):
                continue
            alias_tokens = _tokens(alias)
            if (
                alias_normalized in _VAGUE_ALIASES
                and alias_tokens <= _VAGUE_ALIASES
                and (prompt_tokens - _SIZE_WORDS - _VAGUE_ALIASES)
            ):
                score = 0.35
            else:
                score = 1.0 + len(alias_tokens) / max(len(prompt_tokens), 1)
            if score > best:
                best = score
                best_alias = alias
        if best >= 1.0:
            hits.append((best, tid, best_alias, gold))
    hits.sort(key=lambda row: (-row[0], row[1]))
    return hits


def _match_hybrid(prompt: str, *, gold_only: bool) -> TemplateMatch | None:
    """Lexical + semantic fusion with confidence / margin gates."""

    corrected = correct_typos(prompt)
    items = list(_catalog())
    if not items:
        return None
    items_by_id = {str(item["id"]): item for item in items}
    prompt_tokens = _tokens(corrected)
    if not prompt_tokens and not tokenize(corrected):
        return None

    # Fast path before O(catalog×aliases) lexical scoring.
    exact_hits = _exact_alias_hits(corrected, items)
    if exact_hits:
        best_any = exact_hits[0]
        gold_hits = [row for row in exact_hits if row[3]]
        if gold_only and (not best_any[3]) and best_any[0] >= 1.0:
            if not gold_hits or best_any[0] > gold_hits[0][0]:
                return TemplateMatch(
                    template_id=best_any[1],
                    title=str(items_by_id[best_any[1]].get("title", best_any[1])),
                    score=best_any[0],
                    matched_alias=best_any[2],
                    gold=False,
                    confidence="high",
                    needs_clarify=True,
                    ranking={"mode": "exact_alias_nongold", "score": best_any[0]},
                )
        if gold_hits:
            best_score, best_id, best_alias, best_gold = gold_hits[0]
            second = gold_hits[1][0] if len(gold_hits) > 1 else 0.0
            if best_score - second >= 0.08 or len(gold_hits) == 1:
                if best_id in _DEFAULT_HOUSE_IDS and (
                    prompt_tokens - _SIZE_WORDS - _VAGUE_ALIASES
                ):
                    for score, tid, alias, gold in gold_hits[1:]:
                        if tid not in _DEFAULT_HOUSE_IDS and score >= 0.9:
                            best_score, best_id, best_alias, best_gold = (
                                score,
                                tid,
                                alias,
                                gold,
                            )
                            break
                return TemplateMatch(
                    template_id=best_id,
                    title=str(items_by_id[best_id].get("title", best_id)),
                    score=best_score,
                    matched_alias=best_alias,
                    gold=best_gold,
                    confidence="high",
                    ranking={"mode": "exact_alias", "score": best_score},
                )

    lex_raw = _lexical_scores(corrected, items)
    # Fast path: strong phrase / multi-token alias still wins immediately.
    # Include non-gold so "wizard tower" can beat gold "tower" → watchtower.
    strong_all: list[tuple[float, str, str, bool]] = []
    for tid, (score, alias) in lex_raw.items():
        item = items_by_id[tid]
        if score >= 1.0:
            strong_all.append((score, tid, alias, bool(item.get("gold"))))
    strong_all.sort(key=lambda row: (-row[0], row[1]))
    strong = [row for row in strong_all if (not gold_only) or row[3]]
    if strong_all:
        best_any = strong_all[0]
        best_gold_row = strong[0] if strong else None
        # Prefer a more specific non-gold hit over a weaker gold alias
        # ("wizard tower" / "igloo" must clarify, not paste watchtower / nothing).
        if gold_only and (not best_any[3]) and best_any[0] >= 1.0:
            if best_gold_row is None or best_any[0] > best_gold_row[0]:
                title = str(items_by_id[best_any[1]].get("title", best_any[1]))
                return TemplateMatch(
                    template_id=best_any[1],
                    title=title,
                    score=best_any[0],
                    matched_alias=best_any[2],
                    gold=False,
                    confidence="high",
                    needs_clarify=True,
                    ranking={
                        "mode": "strong_lexical_nongold",
                        "score": best_any[0],
                    },
                )
        if best_gold_row is not None:
            best_score, best_id, best_alias, best_gold = best_gold_row
            second = strong[1][0] if len(strong) > 1 else 0.0
            if best_score - second >= 0.08 or len(strong) == 1:
                if best_id in _DEFAULT_HOUSE_IDS and (
                    prompt_tokens - _SIZE_WORDS - _VAGUE_ALIASES
                ):
                    for score, tid, alias, gold in strong[1:]:
                        if tid not in _DEFAULT_HOUSE_IDS and score >= 0.9:
                            best_score, best_id, best_alias, best_gold = (
                                score,
                                tid,
                                alias,
                                gold,
                            )
                            break
                title = str(items_by_id[best_id].get("title", best_id))
                return TemplateMatch(
                    template_id=best_id,
                    title=title,
                    score=best_score,
                    matched_alias=best_alias,
                    gold=best_gold,
                    confidence="high",
                    ranking={"mode": "strong_lexical", "score": best_score},
                )

    semantic_map: dict[str, float] = {}
    mode = ranker_mode()
    if mode == "hybrid" and backend_enabled():
        idx = get_index()
        idx.ensure_built(items)
        for tid, sim in idx.top_similar(corrected, list(items_by_id), _top_k() * 3):
            semantic_map[tid] = sim
    if not semantic_map:
        # Seed from lexical when embeddings off.
        for tid, (score, _) in sorted(lex_raw.items(), key=lambda x: -x[1][0])[: _top_k()]:
            if score > 0:
                semantic_map[tid] = _normalize_lex(score) * 0.5

    w_lex, w_sem, w_pol = _weights()
    high, medium, margin_need = _confidence_thresholds()
    rows: list[tuple[float, float, float, float, str, str, bool]] = []
    all_ids = set(lex_raw) | set(semantic_map)
    for tid in all_ids:
        item = items_by_id.get(tid)
        if item is None:
            continue
        gold = bool(item.get("gold"))
        if gold_only and not gold:
            continue
        lex_score_raw, alias = lex_raw.get(tid, (0.0, ""))
        lex_n = _normalize_lex(lex_score_raw)
        sem = semantic_map.get(tid, 0.0)
        pol = _category_prior(prompt_tokens, item) + _size_prior(prompt_tokens, item)
        # Keep policy in a small band for fusion.
        pol_n = max(-0.3, min(0.4, pol))
        total = w_lex * lex_n + w_sem * sem + w_pol * (0.5 + pol_n)
        # Preserve raw lexical magnitude for strong-phrase consumers.
        display = max(total, lex_score_raw if lex_score_raw >= 1.0 else total)
        rows.append((display, total, lex_n, sem, tid, alias or tid.replace("_", " "), gold))

    rows.sort(key=lambda row: (-row[1], -row[2], row[4]))
    if not rows:
        if gold_only:
            non_gold = _match_hybrid(prompt, gold_only=False)
            if non_gold is not None and not non_gold.gold:
                return TemplateMatch(
                    template_id=non_gold.template_id,
                    title=non_gold.title,
                    score=non_gold.score,
                    matched_alias=non_gold.matched_alias,
                    gold=False,
                    confidence=non_gold.confidence,
                    alternatives=non_gold.alternatives,
                    needs_clarify=True,
                    ranking=non_gold.ranking,
                )
        return None

    top = rows[0]
    second_total = rows[1][1] if len(rows) > 1 else 0.0
    margin = top[1] - second_total
    alt_ids = [row[4] for row in rows[1:4]]
    alts = _kid_titles(items_by_id, alt_ids)
    # Include the winner title first for clarify messaging.
    clarify_opts = (str(items_by_id[top[4]].get("title", top[4])),) + alts
    clarify_opts = tuple(dict.fromkeys(clarify_opts))[:3]

    ranking = {
        "mode": "hybrid",
        "embedding": backend_enabled() and mode == "hybrid",
        "total": round(top[1], 4),
        "lexical": round(top[2], 4),
        "semantic": round(top[3], 4),
        "margin": round(margin, 4),
        "top": [
            {
                "template_id": row[4],
                "total": round(row[1], 4),
                "lexical": round(row[2], 4),
                "semantic": round(row[3], 4),
            }
            for row in rows[: _top_k()]
        ],
    }

    # Suppress default-house wins on non-house / market / farm vocabulary.
    if top[4] in _DEFAULT_HOUSE_IDS and (
        prompt_tokens & (_MARKET_WORDS | _PLANT_WORDS | _FORT_WORDS | _BRIDGE_WORDS | _CAMP_WORDS)
    ):
        # Skip to next non-default if it is competitively close.
        for row in rows[1:]:
            if row[4] not in _DEFAULT_HOUSE_IDS and row[1] >= medium * 0.8:
                top = row
                second_total = 0.0
                for other in rows:
                    if other[4] != top[4]:
                        second_total = other[1]
                        break
                margin = top[1] - second_total
                alt_ids = [r[4] for r in rows if r[4] != top[4]][:3]
                clarify_opts = (
                    str(items_by_id[top[4]].get("title", top[4])),
                ) + _kid_titles(items_by_id, alt_ids)
                clarify_opts = tuple(dict.fromkeys(clarify_opts))[:3]
                break

    # Camping ask must never paste a crop farm (catastrophic wrong match).
    if prompt_tokens & _CAMP_WORDS and _is_crop_farm(items_by_id.get(top[4], {})):
        camp_rows = [
            row
            for row in rows
            if row[4] in {"campground", "tent_camp"} or "camp" in row[4]
        ]
        if not camp_rows:
            return None
        top = camp_rows[0]
        second_total = 0.0
        for other in rows:
            if other[4] != top[4]:
                second_total = other[1]
                break
        margin = top[1] - second_total
        alt_ids = [r[4] for r in rows if r[4] != top[4]][:3]
        clarify_opts = (
            str(items_by_id[top[4]].get("title", top[4])),
        ) + _kid_titles(items_by_id, alt_ids)
        clarify_opts = tuple(dict.fromkeys(clarify_opts))[:3]

    conf = "low"
    needs_clarify = False
    # Semantic-only ghosts (near-zero lexical) need a stronger margin / score.
    weak_lexical = top[2] < 0.2
    if top[1] >= high and margin >= margin_need and not (weak_lexical and top[3] < 0.5):
        conf = "high"
    elif top[1] >= medium and (
        (not weak_lexical and (margin >= margin_need * 0.5 or top[3] >= 0.35 or top[2] >= 0.7))
        or (weak_lexical and top[3] >= 0.5 and margin >= margin_need)
    ):
        conf = "medium"
        # Medium auto-paste for gold only when semantic/lexical clearly agree.
        if not (
            top[6]
            and (top[2] >= 0.55 or top[3] >= 0.4)
            and margin >= (0.1 if weak_lexical else 0.06)
        ):
            needs_clarify = True
    else:
        # Weak noise (e.g. "make it daytime") must not surface as a template ask.
        return None

    if top[4] in _DEFAULT_HOUSE_IDS and conf != "high":
        needs_clarify = True

    return TemplateMatch(
        template_id=top[4],
        title=str(items_by_id[top[4]].get("title", top[4])),
        score=top[0],
        matched_alias=top[5],
        gold=top[6],
        confidence=conf,
        alternatives=clarify_opts if needs_clarify else alts,
        needs_clarify=needs_clarify,
        ranking=ranking,
    )


def match_template(prompt: str, *, gold_only: bool = True) -> TemplateMatch | None:
    """Match curated templates. By default only gold entries may win auto-paste.

    Live path uses hybrid lexical + local BoW embeddings when
    ``TEMPLATE_RANKER_MODE=hybrid`` and ``TEMPLATE_EMBEDDING_BACKEND=local``
    (defaults). Exact/phrase aliases still short-circuit at high confidence.
    """
    mode = ranker_mode()
    if mode == "lexical_only" or (
        mode != "hybrid" and not backend_enabled()
    ):
        return _match_lexical_only(prompt, gold_only=gold_only)
    if mode == "hybrid" and not backend_enabled():
        return _match_lexical_only(prompt, gold_only=gold_only)
    return _match_hybrid(prompt, gold_only=gold_only)


def clarify_message(match: TemplateMatch) -> str:
    """Kid-friendly top-3 clarification."""

    opts = list(match.alternatives) or [match.title]
    if len(opts) == 1:
        return f"Did you mean {opts[0]}? Or try: little castle, chicken house, or bridge."
    head, *rest = opts
    return f"Did you mean {head}? Other options: {', '.join(rest)}."
