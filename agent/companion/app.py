"""Companion v3 HTTP API — /v1/jobs compatible with NeighborhoodAgent plugin."""

from __future__ import annotations

import os
import re
import uuid
from enum import Enum
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from agent.confirm_tokens import pending_count
from agent.contracts import COMPANION_TOOLS_VERSION, CORE_TOOL_NAMES
from agent.feedback import (
    get_last_job,
    parse_rating_prompt,
    record_feedback,
    remember_last_job,
)
from agent.job import JobRequest
from agent.job_store import JobStore
from agent.loop import run_job
from agent.safety import AuditEntry, append_audit, check_cooldown, utc_now_iso
from agent.skills import list_skills

EVAL_MODE = os.environ.get("AGENT_EVAL_MODE", "").strip() not in ("", "0", "false", "False")
_API_TOKEN_RAW = os.environ.get("AGENT_API_TOKEN", "").strip()
if not _API_TOKEN_RAW and not EVAL_MODE:
    raise RuntimeError(
        "AGENT_API_TOKEN must be set when AGENT_EVAL_MODE is off"
    )
API_TOKEN = _API_TOKEN_RAW or "dev-change-me"

LOCAL_LLM_BASE = os.environ.get(
    "LOCAL_LLM_BASE_URL",
    os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434"),
).rstrip("/")
LOCAL_LLM_MODEL = os.environ.get(
    "LOCAL_LLM_MODEL",
    os.environ.get("OLLAMA_MODEL", "ornith:35b"),
)

ASK_FEEDBACK = os.environ.get("AGENT_ASK_FEEDBACK", "1").strip() not in (
    "0",
    "false",
    "False",
    "",
)
FEEDBACK_HINT = " · Rate: /agent good or /agent bad <why>"

BIND_HOST = os.environ.get("AGENT_BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("AGENT_BIND_PORT", "8787"))

app = FastAPI(title="Neighborhood Companion Agent", version="3.0.0")


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
    tool_calls: list[dict[str, Any]] = []


class Job:
    def __init__(self, job_id: str, request: JobRequest) -> None:
        self.id = job_id
        self.request = request
        self.status = JobStatus.queued
        self.message = ""
        self.steps = 0
        self.model = ""
        self.tool_calls: list[dict[str, Any]] = []
        self.confirm_token: str | None = None
        self.needs_confirm = False


_jobs = JobStore[Job]()


def _auth(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != API_TOKEN:
        raise HTTPException(403, "invalid token")


def _parse_confirm(prompt: str) -> tuple[str | None, str]:
    m = re.match(r"^confirm\s+(\S+)\s+(.*)$", prompt.strip(), re.I | re.S)
    if not m:
        return None, prompt
    return m.group(1), m.group(2)


@app.get("/health")
async def health() -> dict[str, Any]:
    ollama_ok = False
    models: list[str] = []
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{LOCAL_LLM_BASE}/api/tags", timeout=2.0)
            if r.status_code == 200:
                ollama_ok = True
                models = [m.get("name", "") for m in (r.json().get("models") or [])]
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "companion": "3.0.0",
        "tools_version": COMPANION_TOOLS_VERSION,
        "core_tools": list(CORE_TOOL_NAMES),
        "skills": list_skills(),
        "model": LOCAL_LLM_MODEL,
        "ollama_reachable": ollama_ok,
        "ollama_models": models[:20],
        "pending_confirms": pending_count(),
    }


@app.get("/capabilities")
async def capabilities(_: None = Depends(_auth)) -> dict[str, Any]:
    return {
        "companion": "3.0.0",
        "tools_version": COMPANION_TOOLS_VERSION,
        "core_tools": list(CORE_TOOL_NAMES),
        "skills": list_skills(),
    }


@app.post("/v1/jobs", response_model=JobResponse, dependencies=[Depends(_auth)])
async def create_job(req: JobRequest) -> JobResponse:
    # Feedback short-circuit
    rating = parse_rating_prompt(req.prompt)
    if rating is not None:
        try:
            record_feedback(
                player=req.player,
                rating=rating.rating,
                note=rating.note,
                job_id=get_last_job(req.player),
            )
            msg = (
                "Thanks — feedback recorded."
                if rating.rating == "good"
                else "Feedback noted."
            )
        except LookupError as exc:
            msg = str(exc)
        return JobResponse(
            job_id=str(uuid.uuid4()),
            status=JobStatus.done,
            message=msg,
            model="feedback",
        )

    confirm_tok, prompt = _parse_confirm(req.prompt)
    if confirm_tok:
        req = req.model_copy(update={"confirm_token": confirm_tok, "prompt": prompt})

    if not req.eval_mode:
        cool = check_cooldown(req.uuid)
        if cool:
            raise HTTPException(429, cool)

    job_id = str(uuid.uuid4())
    job = Job(job_id, req)
    _jobs.set(job_id, job)
    job.status = JobStatus.running

    outcome = await run_job(req, job_id=job_id)
    job.status = JobStatus.done if outcome.status == "done" else JobStatus.failed
    job.message = outcome.message
    if ASK_FEEDBACK and outcome.status == "done" and outcome.tool_calls and not req.eval_mode:
        if FEEDBACK_HINT not in job.message:
            job.message = job.message + FEEDBACK_HINT
    job.steps = outcome.steps
    job.model = outcome.model
    job.tool_calls = outcome.tool_calls
    job.confirm_token = outcome.confirm_token
    job.needs_confirm = outcome.needs_confirm

    append_audit(
        AuditEntry(
            timestamp=utc_now_iso(),
            player=req.player,
            uuid=req.uuid,
            prompt=req.prompt,
            status=job.status.value,
            model=job.model,
            steps=job.steps,
            tool_calls=job.tool_calls,
            message=job.message,
            dry_run=req.dry_run,
            job_id=job_id,
            routing={"skill": outcome.skill, "companion": "3.0.0"},
        )
    )
    remember_last_job(req.player, job_id)

    return JobResponse(
        job_id=job_id,
        status=job.status,
        message=job.message,
        confirm_token=job.confirm_token,
        needs_confirm=job.needs_confirm,
        steps=job.steps,
        model=job.model,
        tool_calls=job.tool_calls,
    )


@app.get("/v1/jobs/{job_id}", response_model=JobResponse, dependencies=[Depends(_auth)])
async def get_job(job_id: str) -> JobResponse:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")
    return JobResponse(
        job_id=job.id,
        status=job.status,
        message=job.message,
        confirm_token=job.confirm_token,
        needs_confirm=job.needs_confirm,
        steps=job.steps,
        model=job.model,
        tool_calls=job.tool_calls,
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        "agent.companion.app:app",
        host=BIND_HOST,
        port=BIND_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
