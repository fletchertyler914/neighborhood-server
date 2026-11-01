"""Per-player conversation memory for multi-turn sidekick chats."""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol

from companion.routing import RouteDecision, _action, route
from companion.templates import match_template

_MAX_TURNS = 8
_PENDING_TTL_MS = 120_000
_REVISE_TOOLS = frozenset(
    {"finish_wall", "finish_floor", "paste_template", "place_shape"}
)


class SessionPersistence(Protocol):
    def load_player_session(self, player_uuid: str) -> dict[str, Any] | None: ...

    def save_player_session(self, player_uuid: str, payload: dict[str, Any]) -> None: ...


@dataclass
class Turn:
    role: str  # player | sidekick
    text: str
    route: str = ""
    tool: str = ""
    ok: bool = False
    at_ms: int = 0


@dataclass
class PendingClarify:
    original_prompt: str
    question: str
    kind: str = "general"
    slots: dict[str, Any] = field(default_factory=dict)
    created_ms: int = 0


@dataclass
class LastAction:
    tool: str
    arguments: dict[str, Any]
    message: str = ""
    at_ms: int = 0


@dataclass
class PlayerSession:
    turns: deque[Turn] = field(default_factory=lambda: deque(maxlen=_MAX_TURNS))
    pending: PendingClarify | None = None
    last_action: LastAction | None = None

    def remember_player(self, prompt: str) -> None:
        self.turns.append(
            Turn(role="player", text=prompt.strip()[:240], at_ms=int(time.time() * 1000))
        )

    def remember_sidekick(
        self,
        *,
        message: str,
        route: str,
        tool: str = "",
        ok: bool,
    ) -> None:
        self.turns.append(
            Turn(
                role="sidekick",
                text=message.strip()[:240],
                route=route,
                tool=tool,
                ok=ok,
                at_ms=int(time.time() * 1000),
            )
        )

    def history_blob(self) -> list[dict[str, str]]:
        return [
            {
                "role": turn.role,
                "text": turn.text,
                "route": turn.route,
                "tool": turn.tool,
            }
            for turn in self.turns
        ]

    def set_pending(
        self,
        *,
        original_prompt: str,
        question: str,
        kind: str = "general",
        slots: dict[str, Any] | None = None,
    ) -> None:
        self.pending = PendingClarify(
            original_prompt=original_prompt.strip(),
            question=question.strip()[:160],
            kind=kind,
            slots=slots or {},
            created_ms=int(time.time() * 1000),
        )

    def clear_pending(self) -> None:
        self.pending = None

    def pending_alive(self) -> PendingClarify | None:
        if self.pending is None:
            return None
        if int(time.time() * 1000) - self.pending.created_ms > _PENDING_TTL_MS:
            self.pending = None
            return None
        return self.pending

    def remember_action(
        self, *, tool: str, arguments: dict[str, Any], message: str
    ) -> None:
        if tool not in _REVISE_TOOLS:
            return
        self.last_action = LastAction(
            tool=tool,
            arguments=dict(arguments),
            message=message.strip()[:240],
            at_ms=int(time.time() * 1000),
        )

    def to_payload(self) -> dict[str, Any]:
        pending = self.pending_alive()
        return {
            "pending": None
            if pending is None
            else {
                "original_prompt": pending.original_prompt,
                "question": pending.question,
                "kind": pending.kind,
                "slots": pending.slots,
                "created_ms": pending.created_ms,
            },
            "last_action": None
            if self.last_action is None
            else {
                "tool": self.last_action.tool,
                "arguments": self.last_action.arguments,
                "message": self.last_action.message,
                "at_ms": self.last_action.at_ms,
            },
        }

    def load_payload(self, payload: dict[str, Any]) -> None:
        pending_raw = payload.get("pending")
        if isinstance(pending_raw, dict):
            self.pending = PendingClarify(
                original_prompt=str(pending_raw.get("original_prompt") or ""),
                question=str(pending_raw.get("question") or ""),
                kind=str(pending_raw.get("kind") or "general"),
                slots=dict(pending_raw.get("slots") or {}),
                created_ms=int(pending_raw.get("created_ms") or 0),
            )
            self.pending_alive()
        last_raw = payload.get("last_action")
        if isinstance(last_raw, dict) and last_raw.get("tool"):
            self.last_action = LastAction(
                tool=str(last_raw["tool"]),
                arguments=dict(last_raw.get("arguments") or {}),
                message=str(last_raw.get("message") or ""),
                at_ms=int(last_raw.get("at_ms") or 0),
            )


class SessionStore:
    def __init__(self, persistence: SessionPersistence | None = None) -> None:
        self._sessions: dict[str, PlayerSession] = {}
        self._persistence = persistence

    def bind_persistence(self, persistence: SessionPersistence) -> None:
        self._persistence = persistence

    def get(self, player_uuid: str) -> PlayerSession:
        session = self._sessions.get(player_uuid)
        if session is None:
            session = PlayerSession()
            if self._persistence is not None:
                payload = self._persistence.load_player_session(player_uuid)
                if payload:
                    session.load_payload(payload)
            self._sessions[player_uuid] = session
        return session

    def persist(self, player_uuid: str) -> None:
        if self._persistence is None:
            return
        session = self._sessions.get(player_uuid)
        if session is None:
            return
        self._persistence.save_player_session(player_uuid, session.to_payload())


def infer_clarify_kind(prompt: str) -> str:
    text = prompt.lower()
    if re.search(r"\b(floor|ground|pave)\b", text):
        return "floor"
    if re.search(r"\b(wall|walls)\b", text):
        return "wall"
    if re.search(r"\b(build|make|create|place|coop|house|barn|bridge|castle)\b", text):
        return "template"
    if re.search(r"\b(give|bring|hand)\b", text):
        return "give"
    if re.search(r"\b(time|day|night|morning|evening)\b", text):
        return "time"
    if re.search(r"\b(weather|rain|sun|storm)\b", text):
        return "weather"
    return "general"


def resolve_revise(
    *,
    prompt: str,
    session: PlayerSession,
    job_id: str,
) -> RouteDecision | None:
    """Map short revision phrases onto the last verified build action."""
    last = session.last_action
    if last is None:
        return None
    text = " ".join(prompt.strip().split())
    if not text or len(text.split()) > 8:
        return None

    if last.tool == "finish_wall":
        args = dict(last.arguments)
        if re.fullmatch(
            r"(?:please\s+)?(?:make\s+it\s+)?(?:taller|higher|bigger)[.!]?",
            text,
            re.I,
        ):
            height = int(args.get("height") or 8)
            args["height"] = min(128, max(height + 4, 8))
            return RouteDecision(
                route="session.revise_wall_taller",
                tier="A",
                action=_action(job_id, "finish_wall", args, risk="bounded"),
            )
        material_match = re.fullmatch(
            r"(?:please\s+)?(?:use|with|make\s+it)\s+([a-z][a-z0-9 ]{0,40})[.!]?",
            text,
            re.I,
        )
        if material_match:
            from companion.routing import _normalize_material

            material = _normalize_material(material_match.group(1))
            if material:
                args["material"] = material
                return RouteDecision(
                    route="session.revise_wall_material",
                    tier="A",
                    action=_action(job_id, "finish_wall", args, risk="bounded"),
                )

    if last.tool == "finish_floor":
        material_match = re.fullmatch(
            r"(?:please\s+)?(?:use|with|make\s+it)\s+([a-z][a-z0-9 ]{0,40})[.!]?",
            text,
            re.I,
        )
        if material_match:
            from companion.routing import _normalize_material

            material = _normalize_material(material_match.group(1))
            if material:
                mode = str(last.arguments.get("mode") or "replace")
                if mode == "fill":
                    mode = "replace"
                if mode == "clear":
                    mode = "replace"
                return RouteDecision(
                    route="session.revise_floor_material",
                    tier="A",
                    action=_action(
                        job_id,
                        "finish_floor",
                        {"mode": mode, "material": material},
                        risk="bounded",
                    ),
                )

    if last.tool == "place_shape":
        args = dict(last.arguments)
        kind = str(args.get("kind") or "wall")
        if re.fullmatch(
            r"(?:please\s+)?(?:make\s+it\s+)?(?:taller|higher)[.!]?",
            text,
            re.I,
        ):
            height = int(args.get("height") or 4)
            args["height"] = min(32, height + 4)
            return RouteDecision(
                route="session.revise_place_taller",
                tier="A",
                action=_action(job_id, "place_shape", args, risk="bounded"),
            )
        if re.fullmatch(
            r"(?:please\s+)?(?:make\s+it\s+)?(?:bigger|larger)[.!]?",
            text,
            re.I,
        ):
            if kind == "platform":
                args["width"] = min(32, int(args.get("width") or 5) + 2)
                args["depth"] = min(32, int(args.get("depth") or 5) + 2)
            elif kind == "wall":
                args["length"] = min(48, int(args.get("length") or 8) + 4)
                args["height"] = min(32, int(args.get("height") or 4) + 2)
            else:
                args["width"] = min(24, int(args.get("width") or 5) + 2)
                args["depth"] = min(24, int(args.get("depth") or 5) + 2)
                args["height"] = min(24, int(args.get("height") or 4) + 2)
            return RouteDecision(
                route="session.revise_place_bigger",
                tier="A",
                action=_action(job_id, "place_shape", args, risk="bounded"),
            )
        if re.fullmatch(
            r"(?:please\s+)?(?:on\s+top|second\s+floor|upstairs)[.!]?",
            text,
            re.I,
        ):
            return RouteDecision(
                route="session.revise_place_on_top",
                tier="A",
                action=_action(
                    job_id, "finish_floor", {"mode": "fill"}, risk="bounded"
                ),
            )
        material_match = re.fullmatch(
            r"(?:please\s+)?(?:use|with|make\s+it)\s+([a-z][a-z0-9 ]{0,40})[.!]?",
            text,
            re.I,
        )
        if material_match:
            from companion.routing import _normalize_material

            material = _normalize_material(material_match.group(1))
            if material:
                args["material"] = material
                return RouteDecision(
                    route="session.revise_place_material",
                    tier="A",
                    action=_action(job_id, "place_shape", args, risk="bounded"),
                )

    if last.tool == "paste_template" and re.fullmatch(
        r"(?:please\s+)?(?:make\s+it\s+)?(?:bigger|larger)[.!]?",
        text,
        re.I,
    ):
        # Soft revise: ask for a clearer build rather than guessing size.
        return RouteDecision(
            route="session.revise_build_clarify",
            tier="S",
            message="Want a different place instead? Try chicken coop, cottage, or barn.",
            pending_kind="template",
            pending_slots={
                "default_tool": "paste_template",
                "default_arguments": {"template_id": "cottage_medium"},
            },
        )
    return None


def resolve_followup(
    *,
    prompt: str,
    session: PlayerSession,
    job_id: str,
) -> RouteDecision | None:
    """Resolve a short follow-up against pending clarification + recent history."""
    pending = session.pending_alive()
    text = " ".join(prompt.strip().split())
    if not text:
        return None

    revise = resolve_revise(prompt=text, session=session, job_id=job_id)
    if revise is not None and (
        pending is None or pending.kind in {"wall", "floor", "general"}
    ):
        # Prefer revise when there is no give/template/clear pending to finish.
        if pending is None or pending.kind not in {"give", "template", "clear_site"}:
            return revise

    # Affirmations reuse a default action if we stored one.
    # clear_site pending: "yes" → retry paste/shape with clear_site=true.
    if pending and re.fullmatch(
        r"(?:yes|yeah|yep|ok|okay|sure|please|y)[.!]?", text, re.I
    ):
        default = pending.slots.get("default_tool")
        default_args = pending.slots.get("default_arguments")
        if isinstance(default, str) and isinstance(default_args, dict):
            args = dict(default_args)
            if pending.kind == "clear_site":
                args["clear_site"] = True
            return RouteDecision(
                route="session.affirm",
                tier="A",
                action=_action(job_id, default, args, risk="bounded"),
            )

    # Fresh vague builds ("build me a house") must clarify — never let
    # leftover session history auto-paste a cottage.
    primary = route(text, job_id)
    if primary.route == "grammar.clarify_build":
        return None

    candidates = [text]
    if pending:
        candidates.append(f"{pending.original_prompt} {text}")
        candidates.append(text)
    # Also try with the last player turn if no pending.
    for turn in reversed(session.turns):
        if turn.role == "player" and turn.text and turn.text.lower() != text.lower():
            candidates.append(f"{turn.text} {text}")
            break

    # Template follow-ups: "the small one", "chicken coop", "small please".
    # Without a pending clarify, only accept short fragment answers — not
    # full build sentences (those belong to grammar/ranker).
    fragment_ok = (
        pending is not None
        or (
            len(text.split()) <= 4
            and not re.search(
                r"\b(?:build|make|create|construct|put|place)\b", text, re.I
            )
        )
    )
    if fragment_ok and (pending is None or pending.kind in {"template", "general"}):
        for candidate in candidates:
            match = match_template(candidate, gold_only=True)
            if match is None or not match.gold:
                continue
            if match.needs_clarify and pending is None:
                continue
            if pending is not None or re.search(
                r"\b(small|big|large|coop|house|barn|bridge|that|one|cottage|"
                r"market|stall|shop|garden|farm)\b",
                text,
                re.I,
            ):
                from companion.routing import _paste_template_args

                return RouteDecision(
                    route="session.paste_template",
                    tier="A",
                    action=_action(
                        job_id,
                        "paste_template",
                        _paste_template_args(match.template_id, text),
                        risk="bounded",
                    ),
                )

    # Bare amount after a give clarify.
    if pending and pending.kind == "give":
        amount_match = re.fullmatch(r"(\d+)(?:\s+please)?[.!]?", text, re.I)
        material = pending.slots.get("material")
        if amount_match and isinstance(material, str):
            amount = int(amount_match.group(1))
            if 1 <= amount <= 64:
                return RouteDecision(
                    route="session.give_item",
                    tier="S",
                    action=_action(
                        job_id,
                        "give_item",
                        {"material": material, "amount": amount},
                    ),
                )

    # Re-route rewritten candidates through the normal grammar/ranker.
    for candidate in candidates:
        decision = route(candidate, job_id)
        if decision.action is not None:
            return RouteDecision(
                route=f"session.{decision.route}",
                tier=decision.tier,
                action=decision.action,
                message=decision.message,
            )
    return None
