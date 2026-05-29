"""Job request models shared by orchestrator and tests."""

from __future__ import annotations

from pydantic import BaseModel


class JobRequest(BaseModel):
    player: str
    uuid: str
    world: str = "minecraft:overworld"
    x: float = 0
    y: float = 64
    z: float = 0
    gamemode: str = "creative"
    prompt: str
    confirm_token: str | None = None
    dry_run: bool = False
    eval_mode: bool = False
    eval_model: str | None = None
    eval_temperature: float | None = None


def build_user_message(req: JobRequest) -> str:
    return (
        f"Player: {req.player} (uuid={req.uuid})\n"
        f"World: {req.world}\n"
        f"Position: x={req.x:.1f} y={req.y:.1f} z={req.z:.1f}\n"
        f"Gamemode: {req.gamemode}\n"
        f"Prompt: {req.prompt}"
    )
