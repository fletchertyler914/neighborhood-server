"""Tests for keyword retrieval over the knowledge base."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.retrieval import retrieve, render_block


def test_retrieves_glass_for_dome_prompt():
    chunks = retrieve("build a hollow glass dome around me, radius 12")
    sources = {c.source for c in chunks}
    assert "fawe" in sources or "patterns" in sources or "blocks" in sources
    body = " ".join(c.body for c in chunks).lower()
    assert "glass" in body or "sphere" in body


def test_retrieves_quartz_for_platform_prompt():
    chunks = retrieve("21x21 quartz platform at my feet")
    body = " ".join(c.body for c in chunks).lower()
    assert "quartz" in body or "platform" in body


def test_render_block_empty_for_empty_prompt():
    assert render_block("") == ""
