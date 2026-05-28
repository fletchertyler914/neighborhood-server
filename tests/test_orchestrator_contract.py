"""Contract tests for orchestrator job payload (no server)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.job import JobRequest, build_user_message


def test_job_request_bedrock_name():
    req = JobRequest(
        player=".LunarLicense582",
        uuid="00000000-0000-0000-0009-01f42260e0d1",
        prompt="build platform here",
        x=100.5,
        y=80.0,
        z=-50.2,
    )
    msg = build_user_message(req)
    assert ".LunarLicense582" in msg
    assert "build platform" in msg
