from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from companion import PROTOCOL_VERSION, RUNTIME_VERSION
from companion.compound import route_compound
from companion.models import Action, ActionResult, Envelope, JobSubmission
from companion.perception import (
    best_opening,
    model_safe_summary,
    parse_fast_observation,
    parse_semantic_scene,
)
from companion.place_routing import (
    finishable_opening_present,
    rewrite_wall_place_to_finish,
)
from companion.provider import OllamaCompiler
from companion.routing import compiled_route, route
from companion.session import SessionStore, infer_clarify_kind, resolve_followup
from companion.skills import load_skills
from companion.storage import JobStore

try:
    from evals.failure_bundles import write_bundle
except Exception:  # pragma: no cover - optional in slim containers
    write_bundle = None  # type: ignore[assignment]

API_TOKEN = os.environ.get("AGENT_API_TOKEN", "").strip()
if not API_TOKEN:
    raise RuntimeError("AGENT_API_TOKEN must be set")

DB_PATH = Path(
    os.environ.get("COMPANION_DB_PATH", "/var/lib/companion/companion.sqlite3")
)
BIND_HOST = os.environ.get("AGENT_BIND_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("AGENT_BIND_PORT", "8787"))
JOB_DEADLINE_MS = int(os.environ.get("COMPANION_JOB_DEADLINE_MS", "10000"))
logger = logging.getLogger("companion")


class Gateway:
    def __init__(self) -> None:
        self.socket: WebSocket | None = None
        self.server_id: str | None = None
        self.capabilities: set[str] = set()
        self.connected_at_ms: int | None = None
        self._send_lock = asyncio.Lock()
        self._sequence = 0

    async def attach(
        self, socket: WebSocket, *, server_id: str, capabilities: list[str]
    ) -> None:
        if self.socket is not None:
            await self.socket.close(code=4009, reason="superseded gateway")
        self.socket = socket
        self.server_id = server_id
        self.capabilities = set(capabilities)
        self.connected_at_ms = int(time.time() * 1000)
        self._sequence = 0

    def detach(self, socket: WebSocket) -> None:
        if self.socket is socket:
            self.socket = None
            self.server_id = None
            self.capabilities.clear()
            self.connected_at_ms = None

    async def send(self, envelope: Envelope) -> None:
        if self.socket is None:
            raise RuntimeError("Minecraft gateway is offline")
        async with self._send_lock:
            self._sequence += 1
            envelope.sequence = self._sequence
            envelope.sent_at_ms = int(time.time() * 1000)
            await self.socket.send_text(envelope.model_dump_json())


store: JobStore
compiler: OllamaCompiler
skills: dict[str, Any]
sessions = SessionStore()
gateway = Gateway()
action_jobs: dict[str, tuple[str, str, int]] = {}
# job_id -> remaining actions for compound plans
compound_queues: dict[str, list[Action]] = {}
compound_messages: dict[str, list[str]] = {}
job_players: dict[str, str] = {}
observation_waiters: dict[str, asyncio.Future[dict[str, Any]]] = {}
model_status_cache: dict[str, Any] = {
    "reachable": False,
    "installed": False,
    "resident": False,
}
model_compiler_warm = False


CONTEXTUAL_TOOLS = frozenset(
    {"finish_wall", "finish_floor", "paste_template", "place_shape"}
)
_TRY_HINT = " Try: little castle, 5x5 platform, or finish this wall."


async def _request_semantic_scene(
    *,
    envelope: Envelope,
    purpose: str,
    parent_observation_id: str | None,
) -> dict[str, Any] | None:
    if not envelope.job_id:
        return None
    loop = asyncio.get_running_loop()
    future: asyncio.Future[dict[str, Any]] = loop.create_future()
    observation_waiters[envelope.job_id] = future
    try:
        await gateway.send(
            Envelope(
                type="observation.request",
                trace_id=envelope.trace_id,
                job_id=envelope.job_id,
                deadline_ms=envelope.deadline_ms,
                payload={
                    "purpose": purpose,
                    "parent_observation_id": parent_observation_id,
                },
            )
        )
        payload = await asyncio.wait_for(future, timeout=2.0)
        if not payload.get("ok"):
            return None
        scene = payload.get("scene")
        return scene if isinstance(scene, dict) else None
    except Exception:
        return None
    finally:
        observation_waiters.pop(envelope.job_id, None)


async def _monitor_model() -> None:
    global model_status_cache, model_compiler_warm
    while True:
        model_status_cache = await compiler.status()
        if (
            model_status_cache.get("installed")
            and (
                not model_status_cache.get("resident")
                or not model_compiler_warm
            )
        ):
            try:
                await compiler.warm_compiler()
                model_compiler_warm = True
                model_status_cache = await compiler.status()
            except Exception as error:
                logger.warning("compiler warmup failed: %s", error)
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global store, compiler, skills
    store = JobStore(DB_PATH)
    sessions.bind_persistence(store)
    skills = load_skills()
    core_skill = skills.get("neighborhood.core")
    compiler = OllamaCompiler(core_skill.prompt if core_skill else "")
    monitor = asyncio.create_task(_monitor_model())
    try:
        yield
    finally:
        monitor.cancel()
        with suppress(asyncio.CancelledError):
            await monitor


app = FastAPI(
    title="Neighborhood Companion",
    version=RUNTIME_VERSION,
    lifespan=lifespan,
)


def _authorized(socket: WebSocket) -> bool:
    authorization = socket.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        return False
    return authorization.removeprefix("Bearer ").strip() == API_TOKEN


def _spoken_text(message: str) -> str:
    """Kid-facing speakable sentence for a future TTS path (no timing/route jargon)."""
    text = (message or "").strip()
    if not text:
        return ""
    # Drop trailing telemetry fragments if a caller ever concatenates them.
    text = text.split(" · ")[0].strip()
    if len(text) > 160:
        text = text[:157].rstrip() + "..."
    return text


async def _complete(
    *,
    job_id: str,
    trace_id: str,
    ok: bool,
    message: str,
    verified: bool = False,
    route_name: str = "",
    total_ms: int = 0,
    tool: str = "",
    player_uuid: str | None = None,
    clarify: bool = False,
    original_prompt: str = "",
) -> None:
    final_message = message
    if (not ok or clarify) and _TRY_HINT not in message and "Try:" not in message:
        final_message = (message.rstrip() + _TRY_HINT)[:160]
    store.complete_job(job_id, ok=ok, message=final_message, total_ms=total_ms)
    player = player_uuid or job_players.pop(job_id, None)
    if player:
        session = sessions.get(player)
        session.remember_sidekick(
            message=final_message, route=route_name, tool=tool, ok=ok
        )
        try:
            store.save_job_snapshot(
                job_id,
                {
                    "route": route_name,
                    "tool": tool,
                    "ok": ok,
                    "verified": verified,
                    "total_ms": total_ms,
                    "message": final_message,
                    "recent_chat": session.history_blob()[-8:],
                    "prompt": original_prompt,
                },
            )
        except Exception:
            pass
        if clarify:
            session.set_pending(
                original_prompt=original_prompt,
                question=final_message,
                kind=infer_clarify_kind(original_prompt),
            )
        elif ok:
            session.clear_pending()
        sessions.persist(player)
    compound_queues.pop(job_id, None)
    compound_messages.pop(job_id, None)
    await gateway.send(
        Envelope(
            type="job.complete",
            trace_id=trace_id,
            job_id=job_id,
            payload={
                "ok": ok,
                "message": final_message,
                "spoken_text": _spoken_text(final_message),
                "verified": verified,
                "route": route_name,
                "total_ms": total_ms,
            },
        )
    )


async def _dispatch_action(
    *,
    envelope: Envelope,
    action: Action,
    started_ms: int,
) -> None:
    assert envelope.job_id
    store.add_action(
        action_id=action.action_id,
        job_id=envelope.job_id,
        idempotency_key=action.idempotency_key,
        tool=action.tool,
        arguments=action.arguments,
    )
    action_jobs[action.action_id] = (
        envelope.job_id,
        envelope.trace_id,
        started_ms,
    )
    await gateway.send(
        Envelope(
            type="action.execute",
            trace_id=envelope.trace_id,
            job_id=envelope.job_id,
            deadline_ms=envelope.deadline_ms,
            payload=action.model_dump(),
        )
    )


async def _handle_job(envelope: Envelope) -> None:
    if not envelope.job_id:
        return
    started = time.perf_counter()
    started_ms = int(time.time() * 1000)
    model_ms = 0
    submission = JobSubmission.model_validate(envelope.payload)
    store.create_job(
        job_id=envelope.job_id,
        trace_id=envelope.trace_id,
        player_uuid=submission.player.uuid,
        prompt=submission.prompt,
    )
    job_players[envelope.job_id] = submission.player.uuid
    session = sessions.get(submission.player.uuid)
    session.remember_player(submission.prompt)

    feedback = re.fullmatch(
        r"(good|good\s+job|nice|bad)"
        r"(?:\s+(wrong_build|wrong_place|wrong_size|other))?"
        r"(?:\s+(.*))?",
        submission.prompt.strip(),
        re.I | re.S,
    )
    if feedback:
        rating = "bad" if feedback.group(1).lower().startswith("bad") else "good"
        tag = (feedback.group(2) or "").strip().lower()
        note = (feedback.group(3) or "").strip()
        if tag:
            note = f"{tag}: {note}".strip(": ").strip()
        if rating == "bad" and not note:
            store.set_route(envelope.job_id, "feedback", tier="S")
            await _complete(
                job_id=envelope.job_id,
                trace_id=envelope.trace_id,
                ok=True,
                message=(
                    "What went wrong? Try: /agent bad wrong_build "
                    "or /agent bad wrong_place too floaty"
                ),
                route_name="feedback",
                total_ms=int((time.perf_counter() - started) * 1000),
                player_uuid=submission.player.uuid,
                clarify=True,
                original_prompt=submission.prompt,
            )
            return
        store.record_feedback(
            player_uuid=submission.player.uuid,
            rating=rating,
            note=note,
        )
        store.set_route(envelope.job_id, "feedback", tier="S")
        await _complete(
            job_id=envelope.job_id,
            trace_id=envelope.trace_id,
            ok=True,
            message="Thanks! That helps me get better.",
            route_name="feedback",
            total_ms=int((time.perf_counter() - started) * 1000),
            player_uuid=submission.player.uuid,
        )
        return

    # 1) Compound deterministic plans ("make it day and clear the weather")
    compound = route_compound(submission.prompt, envelope.job_id)
    if compound and all(item.action is not None for item in compound):
        first, *rest = compound
        assert first.action is not None
        compound_queues[envelope.job_id] = [item.action for item in rest if item.action]
        compound_messages[envelope.job_id] = []
        store.set_route(
            envelope.job_id,
            "compound." + "+".join(item.action.tool for item in compound if item.action),
            tier="A",
            route_ms=int((time.perf_counter() - started) * 1000),
            model_ms=0,
        )
        if first.action.tool not in gateway.capabilities:
            await _complete(
                job_id=envelope.job_id,
                trace_id=envelope.trace_id,
                ok=False,
                message="I can't do that yet. Try: make it daytime",
                route_name="compound.unsupported",
                total_ms=int((time.perf_counter() - started) * 1000),
                player_uuid=submission.player.uuid,
            )
            return
        await _dispatch_action(
            envelope=envelope, action=first.action, started_ms=started_ms
        )
        return

    fast = parse_fast_observation(submission.observation)
    scene_payload: dict[str, Any] | None = None

    # Prefetch wall geometry when a sized wall ask can finish a visible opening.
    wall_probe = bool(
        re.search(r"\bwalls?\b", submission.prompt, re.I)
        and re.search(r"\d", submission.prompt)
        and not re.search(
            r"\b(?:finish|finsh|complete|fill\s+in|between|remaining|open)\b",
            submission.prompt,
            re.I,
        )
        and fast is not None
    )
    has_finishable_wall = False
    if wall_probe:
        probed = await _request_semantic_scene(
            envelope=envelope,
            purpose="finish_wall",
            parent_observation_id=fast.observation_id if fast else None,
        )
        scene_early = parse_semantic_scene(probed)
        # Busy/unparseable probes must not block the late rewrite retry.
        scene_payload = probed if scene_early is not None else None
        opening = best_opening(scene_early)
        has_finishable_wall = bool(
            opening is not None and opening.confidence in {"high", "medium"}
        )

    # 2) Normal grammar/ranker route
    decision = route(
        submission.prompt,
        envelope.job_id,
        capabilities=(
            set(gateway.capabilities) if gateway.socket is not None else None
        ),
        has_finishable_wall=has_finishable_wall,
    )

    if decision.route == "grammar.cancel":
        session.clear_pending()
        sessions.persist(submission.player.uuid)
        store.set_route(envelope.job_id, decision.route, tier="S")
        await _complete(
            job_id=envelope.job_id,
            trace_id=envelope.trace_id,
            ok=True,
            message=decision.message or "Okay, never mind.",
            route_name=decision.route,
            total_ms=int((time.perf_counter() - started) * 1000),
            player_uuid=submission.player.uuid,
        )
        return

    # 3) Multi-turn follow-up / revise against pending clarification / history.
    # Vague build clarifies must stand — do not let session history auto-paste.
    if decision.action is None and (
        decision.route == "unresolved"
        or (
            decision.route.startswith("grammar.clarify")
            and decision.route != "grammar.clarify_build"
        )
    ):
        follow = resolve_followup(
            prompt=submission.prompt,
            session=session,
            job_id=envelope.job_id,
        )
        if follow is not None:
            decision = follow
            if decision.action is None and decision.message:
                session.set_pending(
                    original_prompt=submission.prompt,
                    question=decision.message,
                    kind=decision.pending_kind or infer_clarify_kind(submission.prompt),
                    slots=decision.pending_slots or {},
                )
                sessions.persist(submission.player.uuid)
                store.set_route(
                    envelope.job_id,
                    decision.route,
                    tier=decision.tier,
                    route_ms=int((time.perf_counter() - started) * 1000),
                )
                await _complete(
                    job_id=envelope.job_id,
                    trace_id=envelope.trace_id,
                    ok=False,
                    message=decision.message,
                    route_name=decision.route,
                    total_ms=int((time.perf_counter() - started) * 1000),
                    player_uuid=submission.player.uuid,
                )
                return

    # 4) Local model compiler with chat memory (+ model-safe perception summary)
    if decision.action is None and decision.route == "unresolved":
        model_started = time.perf_counter()
        try:
            # Lazy Level-1 only when the model truly needs scene context.
            if fast is not None and scene_payload is None and (
                "wall" in submission.prompt.lower()
                or "floor" in submission.prompt.lower()
                or "build" in submission.prompt.lower()
                or "place" in submission.prompt.lower()
            ):
                scene_payload = await _request_semantic_scene(
                    envelope=envelope,
                    purpose="model_context",
                    parent_observation_id=fast.observation_id,
                )
            scene = parse_semantic_scene(scene_payload)
            pending = session.pending_alive()
            intent = await compiler.compile(
                prompt=submission.prompt,
                context={
                    "world": submission.player.world,
                    "gamemode": submission.player.gamemode,
                    "recent_chat": session.history_blob()[-6:],
                    "pending_question": pending.question if pending else "",
                    "perception": model_safe_summary(fast, scene),
                },
            )
            model_ms = int((time.perf_counter() - model_started) * 1000)
            decision = compiled_route(intent, envelope.job_id)
        except Exception:
            model_ms = int((time.perf_counter() - model_started) * 1000)
            decision = type(decision)(
                route="model.unavailable",
                tier="B",
                message="That took too long. Try: make it daytime",
            )

    # Late rewrite: sized place_shape wall → finish_wall when an opening is visible.
    # Retry Level-1 when the wall probe was busy/unparsed/empty so a free-standing
    # place_wall does not win while posts are in view.
    if (
        decision.action is not None
        and decision.action.tool == "place_shape"
        and str(decision.action.arguments.get("kind") or "") == "wall"
        and fast is not None
        and decision.route != "perception.finish_visible_wall"
    ):
        scene = parse_semantic_scene(scene_payload)
        if not finishable_opening_present(scene):
            scene_payload = await _request_semantic_scene(
                envelope=envelope,
                purpose="finish_wall",
                parent_observation_id=fast.observation_id,
            )
            scene = parse_semantic_scene(scene_payload)
        rewritten = rewrite_wall_place_to_finish(
            envelope.job_id,
            decision.action.arguments,
            scene,
        )
        if rewritten is not None:
            decision = rewritten
    # Contextual tools may request a Level-1 inspect; native execute still re-senses.
    elif (
        decision.action is not None
        and decision.action.tool in CONTEXTUAL_TOOLS
        and fast is not None
        and scene_payload is None
    ):
        scene_payload = await _request_semantic_scene(
            envelope=envelope,
            purpose=decision.action.tool,
            parent_observation_id=fast.observation_id,
        )
    route_ms = int((time.perf_counter() - started) * 1000)
    store.set_route(
        envelope.job_id,
        decision.route,
        tier=decision.tier,
        route_ms=route_ms,
        model_ms=model_ms,
    )
    if decision.action is None:
        clarify = "clarify" in decision.route or decision.route == "unresolved"
        if clarify:
            session.set_pending(
                original_prompt=submission.prompt,
                question=decision.message,
                kind=decision.pending_kind or infer_clarify_kind(submission.prompt),
                slots=decision.pending_slots or {},
            )
            sessions.persist(submission.player.uuid)
        if write_bundle is not None:
            with suppress(Exception):
                write_bundle(
                    prompt=submission.prompt,
                    route=decision.route,
                    ok=False,
                    message=decision.message,
                    observation=submission.observation,
                    scene=scene_payload,
                    reason="clarify_or_refuse",
                )
        await _complete(
            job_id=envelope.job_id,
            trace_id=envelope.trace_id,
            ok=False,
            message=decision.message,
            route_name=decision.route,
            total_ms=int((time.perf_counter() - started) * 1000),
            player_uuid=submission.player.uuid,
            clarify=False,  # already set pending above with richer slots
            original_prompt=submission.prompt,
        )
        return
    if decision.action.tool not in gateway.capabilities:
        await _complete(
            job_id=envelope.job_id,
            trace_id=envelope.trace_id,
            ok=False,
            message="I can't do that yet. Try: make it daytime",
            route_name=decision.route,
            total_ms=int((time.perf_counter() - started) * 1000),
            player_uuid=submission.player.uuid,
        )
        return
    await _dispatch_action(
        envelope=envelope, action=decision.action, started_ms=started_ms
    )


async def _handle_action_result(envelope: Envelope) -> None:
    result = ActionResult.model_validate(envelope.payload)
    store.complete_action(result.action_id, result.model_dump())
    correlation = action_jobs.pop(result.action_id, None)
    if correlation is None:
        correlation = store.action_correlation(result.action_id)
    if correlation is None:
        return
    job_id, trace_id, started_ms = correlation
    total_ms = int(time.time() * 1000) - started_ms
    ok = result.ok and result.executed and result.verified
    messages = compound_messages.setdefault(job_id, [])
    if result.message:
        messages.append(result.message)

    queue = compound_queues.get(job_id) or []
    if ok and queue:
        nxt = queue.pop(0)
        compound_queues[job_id] = queue
        store.add_action(
            action_id=nxt.action_id,
            job_id=job_id,
            idempotency_key=nxt.idempotency_key,
            tool=nxt.tool,
            arguments=nxt.arguments,
        )
        action_jobs[nxt.action_id] = (job_id, trace_id, started_ms)
        await gateway.send(
            Envelope(
                type="action.execute",
                trace_id=trace_id,
                job_id=job_id,
                deadline_ms=envelope.deadline_ms,
                payload=nxt.model_dump(),
            )
        )
        return

    combined = " ".join(messages) if messages else result.message
    player_uuid = job_players.get(job_id)
    tool_args = store.action_tool_arguments(result.action_id)
    if ok and player_uuid and tool_args is not None:
        tool_name, arguments = tool_args
        sessions.get(player_uuid).remember_action(
            tool=tool_name,
            arguments=arguments,
            message=combined,
        )
        sessions.persist(player_uuid)
    await _complete(
        job_id=job_id,
        trace_id=trace_id,
        ok=ok,
        verified=result.verified if not messages else ok,
        message=combined,
        total_ms=total_ms,
        tool=tool_args[0] if tool_args else "",
        route_name=store.job_route(job_id),
        player_uuid=player_uuid,
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "runtime": RUNTIME_VERSION,
        "protocol": PROTOCOL_VERSION,
        "gateway_connected": gateway.socket is not None,
        "server_id": gateway.server_id,
        "capabilities": sorted(gateway.capabilities),
        "store": store.counts(),
        "live_metrics": store.live_metrics(),
        "model": model_status_cache,
        "model_compiler_warm": model_compiler_warm,
        "skills": sorted(skills),
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    snapshot = store.metric_snapshot()
    lines = [
        "# HELP companion_gateway_connected Whether the Paper gateway is connected.",
        "# TYPE companion_gateway_connected gauge",
        f"companion_gateway_connected {1 if gateway.socket is not None else 0}",
    ]
    for status, count in snapshot["status"].items():
        lines.append(f'companion_jobs_total{{status="{status}"}} {count}')
    for tier, count in snapshot["tier"].items():
        lines.append(f'companion_jobs_by_tier_total{{tier="{tier}"}} {count}')
    for key in ("route_avg_ms", "model_avg_ms", "total_avg_ms", "total_max_ms"):
        lines.append(f"companion_{key} {snapshot[key]}")
    return "\n".join(lines) + "\n"


@app.websocket("/v1/gateway")
async def gateway_socket(socket: WebSocket) -> None:
    if not _authorized(socket):
        await socket.close(code=4401, reason="unauthorized")
        return
    await socket.accept()
    attached = False
    try:
        while True:
            raw = await socket.receive_text()
            envelope = Envelope.model_validate_json(raw)
            if envelope.type == "hello":
                await gateway.attach(
                    socket,
                    server_id=str(envelope.payload.get("server_id", "default")),
                    capabilities=list(envelope.payload.get("capabilities", [])),
                )
                attached = True
                await gateway.send(
                    Envelope(
                        type="hello.ack",
                        trace_id=envelope.trace_id,
                        payload={
                            "runtime": RUNTIME_VERSION,
                            "protocol": PROTOCOL_VERSION,
                            "heartbeat_ms": 5000,
                        },
                    )
                )
            elif not attached:
                await socket.close(code=4400, reason="hello required")
                return
            elif envelope.type == "heartbeat":
                await gateway.send(
                    Envelope(type="heartbeat", trace_id=envelope.trace_id)
                )
            elif envelope.type == "job.submit":
                if envelope.deadline_ms is None:
                    envelope.deadline_ms = int(time.time() * 1000) + JOB_DEADLINE_MS
                asyncio.create_task(_handle_job(envelope))
            elif envelope.type == "action.result":
                asyncio.create_task(_handle_action_result(envelope))
            elif envelope.type == "observation.result":
                job_id = envelope.job_id
                waiter = observation_waiters.get(job_id) if job_id else None
                if waiter is not None and not waiter.done():
                    waiter.set_result(envelope.payload)
    except WebSocketDisconnect:
        pass
    finally:
        gateway.detach(socket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("companion.app:app", host=BIND_HOST, port=BIND_PORT)

