from __future__ import annotations

import json
import os
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError


class CompiledIntent(BaseModel):
    kind: Literal["action", "clarify", "refuse"]
    tool: (
        Literal[
            "set_time",
            "set_weather",
            "give_item",
            "give_looked_item",
            "summon_entity",
            "paste_template",
            "finish_wall",
            "finish_floor",
            "place_shape",
            "undo_last",
        ]
        | None
    ) = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


_FORMAT_SCHEMA = {
    "type": "object",
    "required": ["kind", "tool", "arguments", "message"],
    "properties": {
        "kind": {"type": "string", "enum": ["action", "clarify", "refuse"]},
        "tool": {
            "type": ["string", "null"],
            "enum": [
                "set_time",
                "set_weather",
                "give_item",
                "give_looked_item",
                "summon_entity",
                "paste_template",
                "finish_wall",
                "finish_floor",
                "place_shape",
                "undo_last",
                None,
            ],
        },
        "arguments": {"type": "object"},
        "message": {"type": "string", "maxLength": 160},
    },
    "additionalProperties": False,
}

_SYSTEM = """You compile a child's Minecraft request into one safe typed action.
Return JSON matching the schema. Never invent a tool.

You may receive recent_chat and pending_question. Use them for short follow-ups
like "the small one", "yes", "16", or "daytime".

Tools:
- set_time: {"time":"day|noon|night|midnight"}
- set_weather: {"weather":"clear|rain|thunder"}
- give_item: {"material":"minecraft material id","amount":1..64}
- give_looked_item: {"amount":1..64?} — give the block the player is looking at
  (these/those/that/this blocks). Omit amount for a stack of 64.
- summon_entity: {"entity":"any summonable mob id","count":1..20}
- paste_template: {"template_id":"snake_case curated gold id","clear_site":true?,"forward_blocks":1..128?}
  Use clear_site when they ask to clear/flatten/make room before building.
  Use forward_blocks when they say e.g. "20 blocks in front".
- finish_wall: {"height":2..128,"material":"optional block id"}
- finish_floor: {"mode":"fill|replace|clear","material":"optional block id"}
- place_shape: {"kind":"wall|platform|box_shell|solid_box|cylinder|bridge|road|path|stairs_to", dims, "material"?}
  For bridge/path across water or a gap, omit length so the native span finds the far shore.
  Prefers gold-block markers when the player placed them.
  For stairs to a door/entrance use kind stairs_to (player should look at or stand near the door).
- mark_route: {"action":"start|finish|cancel|status","kind":"path|bridge","material"?}
  Start marking → player places gold blocks in order → finish connects them.
- undo_last: {}

Rules:
- Only target the requesting player and their current world.
- Players may summon any mob and build/give ordinary Minecraft content.
  Refuse only admin blocks (command/structure/jigsaw/debug stick),
  other-player targeting, and requests unrelated to Minecraft.
- Clarify if the item, amount, mob, time, weather, or build is ambiguous.
- Prefer one clear action. If the child asked for two things, pick the first
  and mention the second in a short clarify message only when needed.
- For "second floor", "next floor", "upper story", or "upstairs floor", use
  finish_floor (mode fill). Do NOT paste_template another whole building.
- For sized walls/platforms/boxes/towers use place_shape, not paste_template.
- Use short, friendly messages without technical words.
- For action, tool and arguments are required and message is empty.
- For clarify/refuse, tool is null, arguments is {}, and message explains briefly.
"""


class OllamaCompiler:
    def __init__(self, skill_prompt: str = "") -> None:
        self.base_url = os.environ.get(
            "LOCAL_LLM_BASE_URL", "http://host.docker.internal:11434"
        ).rstrip("/")
        self.model = os.environ.get("LOCAL_LLM_MODEL", "gemma4:12b-mlx")
        self.timeout = float(os.environ.get("AGENT_LOCAL_MODEL_TIMEOUT_SEC", "5"))
        self.keep_alive = os.environ.get("LOCAL_LLM_KEEP_ALIVE", "30m")
        self.num_ctx = int(os.environ.get("LOCAL_LLM_NUM_CTX", "2048"))
        self.num_predict = int(os.environ.get("LOCAL_LLM_NUM_PREDICT", "192"))
        self.system_prompt = _SYSTEM + (
            "\nSkill guidance:\n" + skill_prompt if skill_prompt else ""
        )

    async def compile(
        self,
        *,
        prompt: str,
        context: dict[str, Any],
        timeout: float | None = None,
    ) -> CompiledIntent:
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "format": _FORMAT_SCHEMA,
            "options": {
                "temperature": 0,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "request": prompt,
                            "context": {
                                key: value
                                for key, value in context.items()
                                if key
                                in {
                                    "world",
                                    "gamemode",
                                    "recent_chat",
                                    "pending_question",
                                    "perception",
                                }
                            },
                        },
                        separators=(",", ":"),
                    ),
                },
            ],
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=timeout or self.timeout,
            )
            response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
        try:
            normalized = _normalize_structured_content(content)
            return CompiledIntent.model_validate(normalized)
        except (ValidationError, ValueError, json.JSONDecodeError) as error:
            sample = " ".join(str(content).split())[:240]
            raise RuntimeError(
                f"local model returned invalid structured output: {sample!r}"
            ) from error

    async def status(self) -> dict[str, Any]:
        result = {
            "model": self.model,
            "mlx_tag": self.model.lower().endswith("-mlx"),
            "reachable": False,
            "installed": False,
            "resident": False,
        }
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                tags_response = await client.get(f"{self.base_url}/api/tags")
                tags_response.raise_for_status()
                names = {
                    item.get("name", "")
                    for item in tags_response.json().get("models", [])
                }
                result["reachable"] = True
                result["installed"] = self.model in names
                running_response = await client.get(f"{self.base_url}/api/ps")
                if running_response.status_code == 200:
                    running = {
                        item.get("name", "")
                        for item in running_response.json().get("models", [])
                    }
                    result["resident"] = self.model in running
        except Exception:
            pass
        return result

    async def prewarm(self) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": self.keep_alive,
                    "options": {"num_ctx": self.num_ctx, "num_predict": 1},
                },
                timeout=max(self.timeout, 30.0),
            )
            response.raise_for_status()

    async def warm_compiler(self) -> None:
        await self.prewarm()
        await self.compile(
            prompt="Warmup request: politely refuse because this is not a Minecraft action.",
            context={"world": "minecraft:overworld", "gamemode": "creative"},
            timeout=max(self.timeout, 20.0),
        )


def _normalize_structured_content(content: str) -> dict[str, Any]:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object")
    data = json.loads(content[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("structured output must be an object")
    if "kind" not in data and "action" in data:
        action = data.pop("action")
        if isinstance(action, dict):
            data.setdefault("arguments", action.get("arguments", {}))
            action = action.get("tool") or action.get("name")
        if action in {"clarify", "refuse"}:
            data["kind"] = action
            data["tool"] = None
        elif isinstance(action, str):
            data["kind"] = "action"
            data["tool"] = action
        else:
            data["tool"] = data.get("tool")
    if "kind" not in data and data.get("tool") is None:
        message = str(data.get("message", "")).lower()
        refusal_markers = ("can't", "cannot", "sorry", "not able", "only help")
        data["kind"] = (
            "refuse" if any(marker in message for marker in refusal_markers) else "clarify"
        )
    data.setdefault("arguments", {})
    data.setdefault("message", "")
    return data

