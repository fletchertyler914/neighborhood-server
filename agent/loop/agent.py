"""One-shot companion loop: fast path or single LLM tool round + canned reply."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from agent.confirm_tokens import (
    consume_confirm_token,
    get_pending_confirm,
    issue_confirm_token,
    store_confirm_payload,
)
from agent.contracts.core import core_openai_schemas, is_core_tool
from agent.dispatch import execute
from agent.job import JobRequest, build_user_message
from agent.llm.client import chat_with_failover
from agent.loop.fast_path import try_fast_path
from agent.safety import new_confirm_token, requires_confirmation
from agent.skills import load_skill, select_skill, schemas_for_skill


@dataclass
class JobOutcome:
    job_id: str
    status: str  # done | failed
    message: str
    model: str = ""
    steps: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    confirm_token: str | None = None
    needs_confirm: bool = False
    skill: str = ""


def _parse_tool_calls(data: dict[str, Any]) -> list[dict[str, Any]]:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    raw = msg.get("tool_calls") or []
    out: list[dict[str, Any]] = []
    for tc in raw:
        fn = tc.get("function") or {}
        name = fn.get("name") or ""
        args_raw = fn.get("arguments") or "{}"
        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {}
        else:
            args = dict(args_raw)
        out.append({"id": tc.get("id") or name, "name": name, "arguments": args})
    return out


def _bind_player(name: str, args: dict[str, Any], player: str) -> None:
    spec_props = None
    try:
        from agent.contracts.core import get_core_definition

        props = get_core_definition(name).parameters.get("properties") or {}
        if "player" in props and not args.get("player"):
            args["player"] = player
    except KeyError:
        if "player" in args or name.endswith("_at_player") or name in (
            "give_item",
            "paste_template_at_player",
            "fawe_sphere_at_player",
            "fawe_cyl_at_player",
        ):
            args.setdefault("player", player)


def _system_prompt(skill_md: str) -> str:
    return (
        "/no_think\n"
        "You are a Minecraft companion agent on a Paper creative server.\n"
        "Call exactly one tool to fulfill the player's request.\n"
        "Prefer paste_template_at_player for named structures (coop, cabin, castle).\n"
        "Prefer fawe_sphere_at_player / fawe_cyl_at_player for sphere/cylinder shape words.\n"
        "Use give_item for items, summon_entity for mobs, set_time/set_weather for world.\n"
        "Keep tool arguments concrete. Do not narrate — call a tool.\n\n"
        f"{skill_md.strip()}\n"
    )


async def run_job(req: JobRequest, *, job_id: str | None = None) -> JobOutcome:
    job_id = job_id or str(uuid.uuid4())
    skill_id = select_skill(req.prompt)
    skill = load_skill(skill_id)

    # Confirm replay: execute stored tool without LLM
    if req.confirm_token:
        pending = get_pending_confirm(req.confirm_token)
        if pending and pending.player == req.player and pending.arguments is not None:
            if consume_confirm_token(
                token=req.confirm_token,
                player=req.player,
                prompt=req.prompt,
                tool=pending.tool,
                arguments=pending.arguments,
            ):
                result = execute(pending.tool, pending.arguments, dry_run=req.dry_run)
                return JobOutcome(
                    job_id=job_id,
                    status="done" if result.ok else "failed",
                    message=result.canned_chat(),
                    model="confirm-replay",
                    steps=1,
                    tool_calls=[
                        {
                            "name": pending.tool,
                            "arguments": pending.arguments,
                            "result": result.model_dump(),
                        }
                    ],
                    skill=skill_id,
                )

    # Fast path
    fast = try_fast_path(req)
    if fast:
        name, args = fast
        return await _execute_one(job_id, req, name, args, model="fast-path", skill_id=skill_id)

    tools = schemas_for_skill(skill_id) or core_openai_schemas()
    messages = [
        {"role": "system", "content": _system_prompt(skill.prompt)},
        {"role": "user", "content": build_user_message(req)},
    ]

    async with httpx.AsyncClient() as client:
        try:
            data, model_used = await chat_with_failover(
                client,
                messages=messages,
                tools=tools,
                temperature=0.0 if req.eval_mode else 0.2,
                model=req.eval_model,
            )
        except Exception as exc:  # noqa: BLE001
            return JobOutcome(
                job_id=job_id,
                status="failed",
                message=f"Model unavailable: {exc}",
                model="",
                skill=skill_id,
            )

    calls = _parse_tool_calls(data)
    if not calls:
        content = (
            ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        ).strip()
        return JobOutcome(
            job_id=job_id,
            status="done",
            message=content or "I need a clearer build or admin request.",
            model=model_used,
            steps=1,
            skill=skill_id,
        )

    tc = calls[0]
    name = tc["name"]
    args = dict(tc["arguments"])
    if not is_core_tool(name) and name not in {t["function"]["name"] for t in tools}:
        return JobOutcome(
            job_id=job_id,
            status="failed",
            message=f"Model chose non-allowed tool: {name}",
            model=model_used,
            steps=1,
            skill=skill_id,
        )
    _bind_player(name, args, req.player)
    return await _execute_one(job_id, req, name, args, model=model_used, skill_id=skill_id)


async def _execute_one(
    job_id: str,
    req: JobRequest,
    name: str,
    args: dict[str, Any],
    *,
    model: str,
    skill_id: str,
) -> JobOutcome:
    if requires_confirmation(name, args):
        token = req.confirm_token
        if not token or not consume_confirm_token(
            token=token,
            player=req.player,
            prompt=req.prompt,
            tool=name,
            arguments=args,
        ):
            new_tok = new_confirm_token()
            issue_confirm_token(
                player=req.player,
                prompt=req.prompt,
                tool=name,
                arguments=args,
                token=new_tok,
            )
            store_confirm_payload(new_tok, args)
            return JobOutcome(
                job_id=job_id,
                status="done",
                message=(
                    f"Destructive action blocked. Confirm with: "
                    f"/agent confirm {new_tok} {req.prompt}"
                ),
                model=model,
                steps=1,
                confirm_token=new_tok,
                needs_confirm=True,
                tool_calls=[{"name": name, "arguments": args, "result": {"ok": False}}],
                skill=skill_id,
            )

    result = execute(name, args, dry_run=req.dry_run, core_only=True)

    return JobOutcome(
        job_id=job_id,
        status="done" if result.ok else "failed",
        message=result.canned_chat(),
        model=model,
        steps=1,
        tool_calls=[{"name": name, "arguments": args, "result": result.model_dump()}],
        skill=skill_id,
    )
