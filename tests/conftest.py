"""Pytest defaults so orchestrator import succeeds in CI without a real token."""

from __future__ import annotations

import os

os.environ.setdefault("AGENT_API_TOKEN", "dev-change-me")
os.environ.setdefault("AGENT_EVAL_MODE", "1")
