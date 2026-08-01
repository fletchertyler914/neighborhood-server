from __future__ import annotations

import time
import uuid
from typing import Any, Literal  # noqa: F401 — Any used by JobSubmission.observation

from pydantic import BaseModel, Field

from companion import PROTOCOL_VERSION

MessageType = Literal[
    "hello",
    "hello.ack",
    "heartbeat",
    "job.submit",
    "job.cancel",
    "job.ask",
    "job.complete",
    "action.execute",
    "action.progress",
    "action.result",
    "observation.request",
    "observation.result",
    "feedback.submit",
    "capabilities.changed",
]


class Envelope(BaseModel):
    protocol: Literal["1.0"] = PROTOCOL_VERSION
    type: MessageType
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str | None = None
    sequence: int = Field(default=0, ge=0)
    sent_at_ms: int = Field(default_factory=lambda: int(time.time() * 1000), ge=0)
    deadline_ms: int | None = Field(default=None, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class PlayerContext(BaseModel):
    name: str
    uuid: str
    world: str
    x: float
    y: float
    z: float
    yaw: float = 0
    pitch: float = 0
    gamemode: str


class JobSubmission(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    player: PlayerContext
    observation: dict[str, Any] | None = None


class Action(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool: str
    arguments: dict[str, Any]
    idempotency_key: str
    risk: Literal["safe", "bounded", "destructive"] = "safe"


class ActionResult(BaseModel):
    action_id: str
    ok: bool
    executed: bool
    verified: bool
    message: str
    execution_ms: int = Field(default=0, ge=0)
    data: dict[str, Any] = Field(default_factory=dict)

