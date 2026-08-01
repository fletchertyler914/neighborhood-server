from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

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
_SIZE_WORDS = frozenset(
    {"little", "small", "tiny", "big", "large", "nice", "cozy", "pretty", "starter"}
)


@dataclass(frozen=True)
class TemplateMatch:
    template_id: str
    title: str
    score: float
    matched_alias: str
    gold: bool = False


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


def is_gold_template(template_id: str) -> bool:
    for item in _catalog():
        if str(item.get("id")) == template_id:
            return bool(item.get("gold"))
    return False


def match_template(prompt: str, *, gold_only: bool = True) -> TemplateMatch | None:
    """Match curated templates. By default only gold entries may win auto-paste."""
    normalized = " ".join(re.findall(r"[a-z0-9]+", prompt.lower()))
    prompt_tokens = _tokens(prompt)
    if not prompt_tokens:
        return None
    ranked: list[TemplateMatch] = []
    for item in _catalog():
        gold = bool(item.get("gold"))
        if gold_only and not gold:
            continue
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
            # Whole-phrase match only — never "house" inside "lighthouse".
            if alias_normalized and re.search(
                rf"(?:^|\s){re.escape(alias_normalized)}(?:\s|$)",
                normalized,
            ):
                if (
                    alias_normalized in _VAGUE_ALIASES
                    and alias_tokens <= _VAGUE_ALIASES
                    and (prompt_tokens - _SIZE_WORDS - _VAGUE_ALIASES)
                ):
                    # "home for my chickens" must not paste cottage via bare "home".
                    score = 0.35
                else:
                    score = 1.0 + len(alias_tokens) / max(len(prompt_tokens), 1)
            elif alias_tokens and alias_tokens <= prompt_tokens:
                # All alias content words appear in the ask (order-independent).
                # Prefer multi-word aliases ("home for chickens") over singles.
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
            ranked.append(
                TemplateMatch(
                    template_id=str(item["id"]),
                    title=str(item.get("title", item["id"])),
                    score=best_score,
                    matched_alias=best_alias,
                    gold=gold,
                )
            )
    ranked.sort(key=lambda match: (-match.score, match.template_id))
    if not ranked:
        # High-confidence non-gold hit → caller may clarify instead of paste.
        if gold_only:
            non_gold = match_template(prompt, gold_only=False)
            if non_gold is not None and not non_gold.gold:
                return TemplateMatch(
                    template_id=non_gold.template_id,
                    title=non_gold.title,
                    score=non_gold.score,
                    matched_alias=non_gold.matched_alias,
                    gold=False,
                )
        return None
    winner = ranked[0]
    runner_up = ranked[1].score if len(ranked) > 1 else 0.0
    if winner.score < 0.72 or winner.score - runner_up < 0.12:
        return None
    # Prefer a more specific non-gold hit over a weaker gold alias
    # ("wizard tower" must not paste watchtower via bare "tower").
    if gold_only and winner.gold:
        non_gold = match_template(prompt, gold_only=False)
        if (
            non_gold is not None
            and not non_gold.gold
            and non_gold.score > winner.score
        ):
            return TemplateMatch(
                template_id=non_gold.template_id,
                title=non_gold.title,
                score=non_gold.score,
                matched_alias=non_gold.matched_alias,
                gold=False,
            )
    return winner

