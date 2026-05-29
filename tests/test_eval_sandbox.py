from __future__ import annotations

from agent.eval.corpus_runner import SandboxGrid, _restore_cell_floor
from agent.eval.world import Box, clear_box


def test_clear_box_chunks_large_volume(monkeypatch):
    commands: list[str] = []

    def fake_rcon(cmd: str, *, timeout: int = 30) -> str:
        commands.append(cmd)
        return ""

    monkeypatch.setattr("agent.eval.world.rcon", fake_rcon)

    clear_box(Box(0, 0, 0, 36, 100, 36))

    assert len(commands) > 1
    assert all(cmd.startswith("fill 0 ") and cmd.endswith(" 36 air replace") for cmd in commands)


def test_sandbox_cell_clears_tall_builds_and_restores_floor(monkeypatch):
    commands: list[str] = []

    def fake_rcon(cmd: str, *, timeout: int = 30) -> str:
        commands.append(cmd)
        return ""

    monkeypatch.setattr("agent.eval.corpus_runner.rcon", fake_rcon)

    cell = SandboxGrid().allocate()

    assert cell.box.y2 - cell.center[1] >= 96

    _restore_cell_floor(cell)

    assert commands == [
        "fill 9982 -63 9982 10018 -61 10018 dirt replace",
        "fill 9982 -60 9982 10018 -60 10018 grass_block replace",
    ]
