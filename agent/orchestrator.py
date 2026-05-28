#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi>=0.115.0",
#   "uvicorn>=0.32.0",
#   "httpx>=0.27.0",
#   "pydantic>=2.9.0",
# ]
# ///
"""Host orchestrator: /agent jobs via local Ollama with optional cloud fallback."""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from agent.job import JobRequest, build_user_message

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from agent import tools as T
from agent.context import gather as gather_context
from agent.retrieval import render_block as render_kb_block
from agent.safety import (
    MAX_AGENT_STEPS,
    append_audit,
    check_cooldown,
    is_destructive_tool,
    new_confirm_token,
    utc_now_iso,
    AuditEntry,
)
from agent.schema import TOOL_SCHEMAS

API_TOKEN = os.environ.get("AGENT_API_TOKEN", "dev-change-me")
OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_FALLBACK_MODEL = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b-instruct")
CLOUD_BASE = os.environ.get("CLOUD_BASE_URL", "https://api.openai.com/v1").rstrip("/")
CLOUD_MODEL = os.environ.get("CLOUD_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
JOB_TIMEOUT = int(os.environ.get("AGENT_JOB_TIMEOUT_SEC", "180"))
LOCAL_MODEL_TIMEOUT = float(os.environ.get("AGENT_LOCAL_MODEL_TIMEOUT_SEC", "20"))
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "512"))
BIND_HOST = os.environ.get("AGENT_BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("AGENT_BIND_PORT", "8787"))

SYSTEM_PROMPT = (_REPO / "agent" / "prompts" / "system.md").read_text(encoding="utf-8")

app = FastAPI(title="Neighborhood Minecraft Agent", version="1.0.0")

# Pending destructive confirmations: token -> expires never (single-use consumed)
_pending_confirms: dict[str, str] = {}


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str = ""
    confirm_token: str | None = None
    needs_confirm: bool = False
    steps: int = 0
    model: str = ""


@dataclass
class Job:
    id: str
    request: JobRequest
    status: JobStatus = JobStatus.queued
    message: str = ""
    steps: int = 0
    model: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


_jobs: dict[str, Job] = {}


def _auth(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != API_TOKEN:
        raise HTTPException(403, "invalid token")


_THINKING_FAMILIES = ("qwen3", "qwen3.5", "qwen3.6", "deepseek-r1", "qwq")


def _is_thinking_model(model: str) -> bool:
    m = model.lower()
    return any(f in m for f in _THINKING_FAMILIES)


async def _chat_completion(
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    api_key: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = f"{base_url}/chat/completions"
    is_ollama = "11434" in base_url or base_url.endswith("ollama")
    if is_ollama:
        url = f"{base_url}/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": TOOL_SCHEMAS,
        "tool_choice": "auto",
        "temperature": 0.2,
    }
    if is_ollama:
        payload["options"] = {
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_NUM_PREDICT,
        }
    if is_ollama and _is_thinking_model(model):
        payload["think"] = False
    resp = await client.post(url, headers=headers, json=payload, timeout=timeout or JOB_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _parse_tool_calls(choice: dict[str, Any]) -> list[dict[str, Any]]:
    msg = choice.get("message", {})
    calls = msg.get("tool_calls") or []
    out: list[dict[str, Any]] = []
    for call in calls:
        fn = call.get("function", {})
        name = fn.get("name", "")
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        out.append({"id": call.get("id", name), "name": name, "arguments": args})
    return out


def _build_smart_context(req: JobRequest) -> str:
    """Assemble the upgraded user message: prompt + live world + KB chunks."""
    parts = [build_user_message(req)]
    try:
        ctx = gather_context(req.player, req.x, req.y, req.z)
        parts.append("")
        parts.append(ctx.render())
    except Exception:
        pass
    kb = render_kb_block(req.prompt)
    if kb:
        parts.append("")
        parts.append(kb)
    return "\n".join(parts)


async def _run_agent_loop(job: Job) -> None:
    req = job.request
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_smart_context(req)},
    ]
    model_used = ""
    failure_streak: dict[str, int] = {}
    LOOP_BREAK_AT = 2
    async with httpx.AsyncClient() as client:
        for step in range(MAX_AGENT_STEPS):
            job.steps = step + 1
            data: dict[str, Any] | None = None
            last_err: Exception | None = None

            # Local-first, but never let a slow local model freeze in-game chat.
            for candidate in [OLLAMA_MODEL, OLLAMA_FALLBACK_MODEL]:
                if data is not None or not candidate:
                    continue
                try:
                    data = await _chat_completion(
                        client,
                        OLLAMA_BASE,
                        candidate,
                        messages,
                        timeout=LOCAL_MODEL_TIMEOUT,
                    )
                    model_used = f"ollama:{candidate}"
                except Exception as e:
                    last_err = e

            # Cloud fallback
            if data is None and OPENAI_API_KEY:
                try:
                    data = await _chat_completion(
                        client,
                        CLOUD_BASE,
                        CLOUD_MODEL,
                        messages,
                        api_key=OPENAI_API_KEY,
                    )
                    model_used = f"cloud:{CLOUD_MODEL}"
                except Exception as e:
                    last_err = e

            if data is None:
                job.status = JobStatus.failed
                job.message = f"No model available: {last_err}"
                job.model = model_used
                return

            job.model = model_used
            choice = data["choices"][0]
            tool_calls = _parse_tool_calls(choice)
            assistant_msg = choice.get("message", {})
            messages.append(assistant_msg)

            if not tool_calls:
                job.status = JobStatus.done
                job.message = (assistant_msg.get("content") or "Done.").strip()
                return

            for tc in tool_calls:
                name = tc["name"]
                args = tc["arguments"]
                player_tools = {
                    "fawe_as_player",
                    "fawe_sphere_at_player",
                    "fawe_cyl_at_player",
                    "mine_shaft_at_player",
                    "get_player_position",
                    "get_player_dimension",
                    "give_haste",
                    "teleport_player",
                    "set_gamemode",
                }
                if name in player_tools and "player" not in args:
                    args["player"] = req.player

                if is_destructive_tool(name, args):
                    token = req.confirm_token
                    if not token or token not in _pending_confirms:
                        new_tok = new_confirm_token()
                        _pending_confirms[new_tok] = req.prompt
                        job.status = JobStatus.done
                        job.message = (
                            f"Destructive action blocked. Confirm with: "
                            f"/agent confirm {new_tok} {req.prompt}"
                        )
                        return
                    del _pending_confirms[token]

                result = T.execute_tool(name, args, dry_run=req.dry_run)
                job.tool_calls.append(
                    {"name": name, "arguments": args, "result": result.to_dict()}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", name),
                        "content": json.dumps(result.to_dict()),
                    }
                )

                signature = f"{name}:{json.dumps(args, sort_keys=True)}"
                if not result.ok:
                    failure_streak[signature] = failure_streak.get(signature, 0) + 1
                    if failure_streak[signature] >= LOOP_BREAK_AT:
                        job.status = JobStatus.failed
                        job.message = (
                            f"Aborting: {name} failed {failure_streak[signature]}x with the same "
                            f"arguments. Last error: {result.error or result.output}"
                        )
                        return
                else:
                    failure_streak[signature] = 0

        job.status = JobStatus.done
        job.message = "Reached max agent steps; partial work may have been applied."


async def _process_job(job_id: str) -> None:
    job = _jobs[job_id]
    job.status = JobStatus.running
    try:
        await _run_agent_loop(job)
    except Exception as e:
        job.status = JobStatus.failed
        job.message = str(e)
    append_audit(
        AuditEntry(
            timestamp=utc_now_iso(),
            player=job.request.player,
            uuid=job.request.uuid,
            prompt=job.request.prompt,
            status=job.status.value,
            model=job.model,
            steps=job.steps,
            tool_calls=job.tool_calls,
            message=job.message,
            dry_run=job.request.dry_run,
        )
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/jobs", response_model=JobResponse, dependencies=[Depends(_auth)])
async def create_job(req: JobRequest) -> JobResponse:
    cooldown_msg = check_cooldown(req.uuid)
    if cooldown_msg:
        raise HTTPException(429, cooldown_msg)

    # /agent confirm <token> <prompt>
    prompt = req.prompt.strip()
    if prompt.lower().startswith("confirm "):
        parts = prompt.split(maxsplit=2)
        if len(parts) >= 3:
            req.confirm_token = parts[1]
            req.prompt = parts[2]

    job_id = str(uuid.uuid4())
    job = Job(id=job_id, request=req)
    _jobs[job_id] = job

    await _process_job(job_id)

    return JobResponse(
        job_id=job_id,
        status=job.status,
        message=job.message,
        steps=job.steps,
        model=job.model,
    )


@app.get("/v1/jobs/{job_id}", response_model=JobResponse, dependencies=[Depends(_auth)])
async def get_job(job_id: str) -> JobResponse:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return JobResponse(
        job_id=job_id,
        status=job.status,
        message=job.message,
        steps=job.steps,
        model=job.model,
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        "agent.orchestrator:app",
        host=BIND_HOST,
        port=BIND_PORT,
        reload=False,
        factory=False,
    )


if __name__ == "__main__":
    main()
