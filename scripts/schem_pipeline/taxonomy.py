"""Map listing titles/tags → catalog intent ids (CURATED_REFILL / gold gaps)."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.list_gold_gaps import GAPS  # noqa: E402

# Strong keyword → intent. Order matters: first match wins among equal scores.
INTENT_KEYWORDS: dict[str, list[str]] = {
    "chicken_coop_small": [
        "chicken coop",
        "hen house",
        "henhouse",
        "chicken pen",
        "chicken house",
        "coop",
    ],
    "barn_red_large": ["red barn", "barn with silo", "farm barn", "barn"],
    "pig_pen_small": ["pig pen", "pig sty", "pigsty", "pig enclosure"],
    "sheep_pen_medium": ["sheep pen", "sheep enclosure", "sheep fold"],
    "bee_apiary_small": ["bee house", "apiary", "beehive house", "bee farm", "honeycomb"],
    "garden_plot": ["flower garden", "garden plot", "cottage garden", "flower bed"],
    "market_stall": ["market stall", "shop stall", "vendor stall", "market booth", "stall"],
    "workshop_small": ["workshop", "carpenter", "tool shed", "smithy shop"],
    "lighthouse_short": ["lighthouse"],
    "well_village": ["village well", "wishing well", "well"],
    "house_cottage_small": ["cottage", "starter house", "small house", "tiny house"],
    "cabin_log": ["log cabin", "cabin", "spruce cabin", "wood cabin"],
    "treehouse_oak": ["treehouse", "tree house"],
    "castle_small_keep": ["castle", "keep", "fortress"],
    "storage_shed": ["storage shed", "garden shed", "shed"],
    "mill_water": ["water mill", "watermill", "waterwheel"],
    "greenhouse_small": ["greenhouse"],
    "fountain_small": ["fountain"],
    "gazebo_oak": ["gazebo"],
    "playground_small": ["playground", "swing"],
    "igloo_small": ["igloo"],
    "bridge_rope": ["rope bridge"],
    "bridge_stone_long": ["stone bridge", "arch bridge"],
    "pier_long": ["pier", "boardwalk"],
    "campground": ["campground", "camp site", "campsite"],
    "bakery_small": ["bakery", "bakehouse"],
    "fishing_hut": ["fishing hut", "fisherman", "fishing shack"],
    "library_small": ["library", "bookstore"],
    "blacksmith_shop": ["blacksmith", "forge", "smithy"],
    "tavern_small": ["tavern", "pub", "inn tavern"],
    "windmill_small": ["windmill"],
    "watchtower_tall": ["watchtower", "guard tower"],
    "wizard_tower": ["wizard tower", "mage tower"],
    "church_small": ["church", "chapel", "stave church"],
    "inn_small": ["inn"],
}

NEGATIVE_KEYWORDS = (
    "creeper farm",
    "afk farm",
    "xp farm",
    "iron farm",
    "mob farm",
    "redstone",
    "duper",
    "unbundler",
    "pixel art",
    "statue",
    "map art",
)

# Landmark / showpiece / furnished-base intents — SchemCraft megas OK when
# the title honestly names the structure (castle, tavern, wizard tower, …).
LANDMARK_INTENTS = frozenset(
    {
        "castle_small_keep",
        "gothic_cathedral",
        "wizard_tower",
        "church_small",
        "inn_small",
        "tavern_small",
        "blacksmith_shop",
        "treehouse_oak",
        "house_cottage_small",
        "cottage_medium",
        "bakery_small",
        "fishing_hut",
        "library_small",
    }
)

# Simple kid structures: do NOT accept SchemCraft-style
# "Ultimate … Survival Base/House" titles (feature word ≠ the structure).
# Source these from Bloxelizer / Abfielder / MCBuild / PhantomMarket with
# small block-count filters, or keep parametric place_shape.
BASIC_STRUCTURE_INTENTS = frozenset(
    {
        "chicken_coop_small",
        "barn_red_large",
        "pig_pen_small",
        "sheep_pen_medium",
        "bee_apiary_small",
        "garden_plot",
        "market_stall",
        "workshop_small",
        "lighthouse_short",
        "well_village",
        "windmill_small",
        "watchtower_tall",
        "cabin_log",
        "storage_shed",
        "mill_water",
        "greenhouse_small",
        "fountain_small",
        "gazebo_oak",
        "playground_small",
        "bridge_rope",
        "bridge_stone_long",
        "pier_long",
        "igloo_small",
    }
)

# "Fantasy Windmill Survival House", "Ultimate … Survival Base", etc.
_SURVIVAL_BASE_OR_HOUSE = re.compile(
    r"\bsurvival\s+(?:base|house|home|starter)\b"
    r"|\bultimate\b.+\b(?:base|house|home)\b"
    r"|\bstarter\s+(?:survival\s+)?(?:base|house|home)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Match:
    intent_id: str
    score: float
    reason: str


def open_gap_ids(*, prio: str = "P0", include_gold: bool = False) -> list[str]:
    """Catalog intent ids that still need gold (or all gap ids if include_gold)."""
    import json

    catalog = json.loads((REPO_ROOT / "agent" / "templates" / "catalog.json").read_text())
    gold = {
        str(t.get("id")): bool(t.get("gold"))
        for t in (catalog.get("templates") or [])
        if t.get("id")
    }
    prios = ["P0", "P1", "P2"] if prio == "all" else [prio]
    out: list[str] = []
    for p in prios:
        for tid, _ask, _notes in GAPS.get(p, []):
            if gold.get(tid) and not include_gold:
                continue
            out.append(tid)
    return out


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def is_survival_base_title(text: str) -> bool:
    """True for Ultimate/Fantasy … Survival Base/House style listings."""
    return bool(text and _SURVIVAL_BASE_OR_HOUSE.search(text))


def match_intent(
    *,
    title: str,
    tags: list[str] | None = None,
    description: str = "",
    allowed_intents: set[str] | None = None,
) -> Match | None:
    """Return best catalog intent match, or None if no gap keyword hits."""
    blob = _norm(" ".join([title or "", description or "", " ".join(tags or [])]))
    if not blob:
        return None
    if any(neg in blob for neg in NEGATIVE_KEYWORDS):
        return None

    best: Match | None = None
    for intent_id, kws in INTENT_KEYWORDS.items():
        if allowed_intents is not None and intent_id not in allowed_intents:
            continue
        for kw in kws:
            if kw in blob:
                # Longer keyword → stronger match; whole-word-ish bonus.
                score = 10.0 + len(kw)
                if re.search(rf"\b{re.escape(kw)}\b", blob):
                    score += 5.0
                # Prefer exact-ish title hits.
                if kw in _norm(title):
                    score += 8.0
                cand = Match(intent_id=intent_id, score=score, reason=f"keyword:{kw}")
                if best is None or cand.score > best.score:
                    best = cand
                break  # next intent

    if best is None:
        return None

    # Basics: reject SchemCraft mega "survival house/base" titles even when a
    # feature keyword matches (windmill ⊂ fantasy windmill survival house).
    if best.intent_id in BASIC_STRUCTURE_INTENTS and is_survival_base_title(blob):
        return None

    return best


def max_blocks_for_intent(intent_id: str, *, basic: int, landmark: int) -> int:
    return landmark if intent_id in LANDMARK_INTENTS else basic
