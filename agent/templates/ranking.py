"""Hybrid template ranking: lexical + semantic candidates, deterministic policy rerank."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from agent.templates import catalog as template_catalog
from agent.templates.embedding_backend import backend_enabled, get_index

ConfidenceLevel = Literal["high", "medium", "low", "none"]

_SIZE_HINTS = {
    "tiny": "basic",
    "small": "basic",
    "medium": "common",
    "large": "complex",
    "big": "common",
    "huge": "complex",
    "tall": "common",
}


@dataclass(frozen=True)
class CandidateScore:
    template_id: str
    total: float
    lexical: float
    semantic: float
    policy: float
    reasons: tuple[str, ...] = ()


@dataclass
class RankedTemplateResult:
    query: str
    selected_template_id: str | None
    confidence: ConfidenceLevel
    confidence_score: float
    top_candidates: tuple[CandidateScore, ...] = ()
    disambiguation_message: str = ""
    score_breakdown: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "selected_template_id": self.selected_template_id,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "top_candidates": [
                {
                    "template_id": c.template_id,
                    "total": round(c.total, 4),
                    "lexical": round(c.lexical, 4),
                    "semantic": round(c.semantic, 4),
                    "policy": round(c.policy, 4),
                    "reasons": list(c.reasons),
                }
                for c in self.top_candidates
            ],
            "disambiguation_message": self.disambiguation_message,
            "score_breakdown": self.score_breakdown,
        }


def _ranker_mode() -> str:
    return os.environ.get("TEMPLATE_RANKER_MODE", "hybrid").strip().lower()


def _top_k() -> int:
    return max(3, min(int(os.environ.get("TEMPLATE_RANK_TOP_K", "8")), 20))


def _confidence_high() -> float:
    return float(os.environ.get("TEMPLATE_CONFIDENCE_HIGH", "0.72"))


def _confidence_medium() -> float:
    return float(os.environ.get("TEMPLATE_CONFIDENCE_MEDIUM", "0.45"))


def _lexical_score(query: str, meta: template_catalog.TemplateMeta) -> float:
    """Delegate to catalog resolver; map hit/miss to 0..1."""

    needle = query.strip().lower()
    if not needle:
        return 0.0
    # Exact id
    if needle.replace(" ", "_") == meta.id:
        return 1.0
    pool: list[tuple[str, bool]] = [(a, True) for a in meta.aliases]
    pool.extend((t, False) for t in meta.tags)
    pool.append((meta.title.lower(), True))
    pool.append((meta.id.replace("_", " "), True))
    best = 0.0
    for phrase, explicit in pool:
        al = phrase.lower().strip()
        if not al or len(al) < 2:
            continue
        if al not in needle and not (
            len(al) >= 4 and al in needle.replace("-", " ")
        ):
            if not re.search(rf"(?:^|\W){re.escape(al)}(?:\W|$)", needle):
                continue
        score = min(1.0, len(al) / max(len(needle), 1))
        if re.search(rf"(?:^|\W){re.escape(al)}(?:\W|$)", needle):
            score += 0.5
        if explicit:
            score += 0.3
        if " " in al:
            score += 0.2
        best = max(best, min(1.0, score))
    return best


def _policy_boost(query: str, meta: template_catalog.TemplateMeta, *, intent_family: str) -> float:
    boost = 0.0
    reasons: list[str] = []
    q = query.lower()
    if intent_family and meta.category == "farm" and intent_family == "farm_pen":
        boost += 0.15
        reasons.append("farm_pen_intent")
    if intent_family == "castle" and meta.category == "fortress":
        boost += 0.12
        reasons.append("castle_intent")
    if any(w in q for w in ("fortress", "keep", "stone castle", "stone fortress")):
        if meta.id == "castle_small_keep":
            boost += 0.2
            reasons.append("fortress_keep_alias")
            if "stone" in q and "fortress" in q:
                boost += 0.15
                reasons.append("stone_fortress_keep")
        elif meta.id == "fortress_medium":
            if "stone" in q and "fortress" in q and "keep" not in q:
                boost -= 0.08
                reasons.append("defer_to_keep")
            elif "fortress" in q and "keep" not in q:
                boost += 0.05
                reasons.append("fortress_word")
    if "wooden" in q and "bridge" in q and "suspension" not in q and "rope" not in q:
        if meta.id == "bridge_oak_short":
            boost += 0.22
            reasons.append("wooden_bridge_short")
        elif meta.id == "bridge_wood_suspension":
            boost -= 0.1
            reasons.append("wooden_bridge_not_suspension")
    if intent_family == "bridge" and "bridge" in meta.id:
        boost += 0.15
        reasons.append("bridge_intent")
    if intent_family == "house" and meta.category == "house":
        boost += 0.1
        reasons.append("house_intent")
    for word, complexity in _SIZE_HINTS.items():
        if word in q and meta.complexity == complexity:
            boost += 0.08
            reasons.append(f"size_{word}")
            break
    if template_catalog.schematic_repo_path(meta).is_file():
        boost += 0.05
        reasons.append("has_schem")
    return boost


def _merge_candidates(
    query: str,
    lexical_map: dict[str, float],
    semantic_map: dict[str, float],
    *,
    intent_family: str,
) -> list[CandidateScore]:
    all_ids = set(lexical_map) | set(semantic_map)
    rows: list[CandidateScore] = []
    for tid in all_ids:
        try:
            meta = template_catalog.find_template(tid)
        except ValueError:
            continue
        lex = lexical_map.get(tid, 0.0)
        sem = semantic_map.get(tid, 0.0)
        pol = _policy_boost(query, meta, intent_family=intent_family)
        reasons: list[str] = []
        if lex >= 0.5:
            reasons.append("strong_lexical")
        if sem >= 0.4:
            reasons.append("semantic_match")
        if pol > 0:
            reasons.append("policy_boost")
        # Weighted fusion (deterministic)
        w_lex = float(os.environ.get("TEMPLATE_RANK_W_LEX", "0.55"))
        w_sem = float(os.environ.get("TEMPLATE_RANK_W_SEM", "0.30"))
        w_pol = float(os.environ.get("TEMPLATE_RANK_W_POL", "0.15"))
        total = w_lex * lex + w_sem * sem + w_pol * min(1.0, pol * 3)
        rows.append(
            CandidateScore(
                template_id=tid,
                total=total,
                lexical=lex,
                semantic=sem,
                policy=pol,
                reasons=tuple(reasons),
            )
        )
    rows.sort(key=lambda c: (-c.total, -c.lexical, -len(c.template_id), c.template_id))
    return rows


def _share_root(a: str, b: str) -> bool:
    """Do two template ids share the same semantic root (e.g. chicken_coop)?"""

    def root(tid: str) -> str:
        parts = tid.split("_")
        if parts and parts[-1] in {"small", "medium", "large", "tall", "short", "long", "tiny"}:
            parts = parts[:-1]
        return "_".join(parts)

    return root(a) == root(b)


def _confidence_from_scores(rows: list[CandidateScore]) -> tuple[ConfidenceLevel, float, str]:
    if not rows:
        return "none", 0.0, ""
    top = rows[0]
    second = rows[1].total if len(rows) > 1 else 0.0
    margin = top.total - second
    score = top.total
    hi = _confidence_high()
    med = _confidence_medium()
    if score >= hi and margin >= 0.12:
        return "high", score, ""
    if score >= med:
        alts = [r.template_id for r in rows[1:4]]
        titles = []
        for tid in alts:
            try:
                titles.append(template_catalog.find_template(tid).title)
            except ValueError:
                titles.append(tid)
        msg = (
            f"Did you mean «{template_catalog.find_template(top.template_id).title}»? "
            f"Other options: {', '.join(titles)}."
            if titles
            else ""
        )
        return "medium", score, msg
    alts = ", ".join(r.template_id.replace("_", " ") for r in rows[:3])
    return "low", score, f"I found several possibilities: {alts}. What kind of structure?"


def resolve_template(
    query: str,
    *,
    intent_family: str = "",
    category: str | None = None,
) -> RankedTemplateResult:
    """Single entrypoint: natural language -> ranked template selection."""

    template_catalog._build_index()
    q = (query or "").strip()
    if not q:
        return RankedTemplateResult(
            query=q,
            selected_template_id=None,
            confidence="none",
            confidence_score=0.0,
        )

    # Fast path: legacy resolver only when the input is short / direct
    # (an id, alias, or 1-2 token natural-language phrase). For longer
    # NL queries, the hybrid ranker is more reliable than substring matching.
    legacy = template_catalog.resolve_template_id(q)
    short_query = len(q.split()) <= 2
    has_size = bool(re.search(r"\b(small|tiny|medium|large|big)\b", q.lower()))
    if legacy and short_query and not has_size:
        meta = template_catalog.find_template(legacy)
        row = CandidateScore(
            template_id=legacy,
            total=1.0,
            lexical=1.0,
            semantic=1.0,
            policy=0.0,
            reasons=("legacy_exact",),
        )
        legacy_result = RankedTemplateResult(
            query=q,
            selected_template_id=legacy,
            confidence="high",
            confidence_score=1.0,
            top_candidates=(row,),
            score_breakdown={"mode": "legacy_exact", "template": legacy},
        )
        try:
            from agent.templates.ranking_audit import append_ranking_audit

            append_ranking_audit(legacy_result, source="legacy_exact")
        except OSError:
            pass
        return legacy_result

    metas = list(template_catalog.iter_templates(category=category))
    if not metas:
        metas = list(template_catalog.iter_templates())

    lexical_map: dict[str, float] = {}
    for meta in metas:
        lexical_map[meta.id] = _lexical_score(q, meta)

    semantic_map: dict[str, float] = {}
    mode = _ranker_mode()
    if mode == "hybrid" and backend_enabled():
        idx = get_index()
        idx.ensure_built(metas)
        for tid, sim in idx.top_similar(q, [m.id for m in metas], _top_k()):
            semantic_map[tid] = sim
    elif mode == "lexical_only":
        pass

    # Seed semantic from top lexical when embeddings disabled
    if not semantic_map:
        lex_sorted = sorted(lexical_map.items(), key=lambda x: -x[1])[:_top_k()]
        for tid, sc in lex_sorted:
            if sc > 0:
                semantic_map[tid] = sc * 0.5

    rows = _merge_candidates(q, lexical_map, semantic_map, intent_family=intent_family)
    top_slice = tuple(rows[: _top_k()])
    conf, conf_score, dis_msg = _confidence_from_scores(rows)

    # Strong semantic match should still trip medium confidence even when
    # lexical is weak (e.g. "a place for chickens to live" -> chicken coop,
    # "big mansion" -> house variants). Otherwise small models that phrase
    # things creatively get useless "low" answers.
    if conf == "low" and rows:
        top = rows[0]
        second_sem = rows[1].semantic if len(rows) > 1 else 0.0
        # When two top results are size-variants of the same root ("chicken_coop_*"),
        # treat them as a single intent and surface the more "neutral" one.
        margin_sem = top.semantic - second_sem
        if (
            (top.semantic >= 0.35 and margin_sem >= 0.02)
            or (top.semantic >= 0.6)
            or (top.semantic >= 0.25 and margin_sem >= 0.12)
            or (
                top.semantic >= 0.3
                and len(rows) > 1
                and _share_root(top.template_id, rows[1].template_id)
            )
        ):
            conf = "medium"
            conf_score = max(conf_score, 0.5)
            try:
                dis_msg = (
                    f"Best guess: «{template_catalog.find_template(top.template_id).title}». "
                    "If that's not it, name the structure (e.g. 'cottage', 'pen', 'tower')."
                )
            except ValueError:
                pass

    selected: str | None = None
    if conf in ("high", "medium") and rows:
        selected = rows[0].template_id
    elif conf == "low" and rows and rows[0].total >= _confidence_medium() * 0.85:
        selected = rows[0].template_id

    result = RankedTemplateResult(
        query=q,
        selected_template_id=selected,
        confidence=conf,
        confidence_score=conf_score,
        top_candidates=top_slice,
        disambiguation_message=dis_msg,
        score_breakdown={
            "mode": mode,
            "embedding": backend_enabled(),
            "candidate_count": len(rows),
            "margin": round(rows[0].total - (rows[1].total if len(rows) > 1 else 0.0), 4)
            if rows
            else 0.0,
        },
    )
    try:
        from agent.templates.ranking_audit import append_ranking_audit

        append_ranking_audit(result, source="resolve_template")
    except OSError:
        pass
    return result


def infer_best_template_id(prompt: str, *, intent_family: str = "") -> str | None:
    """Convenience wrapper used by orchestrator and catalog."""

    return resolve_template(prompt, intent_family=intent_family).selected_template_id
