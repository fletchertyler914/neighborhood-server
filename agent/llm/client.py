"""Thin OpenAI-compat client for local inference (Ollama on Apple Silicon)."""

from __future__ import annotations

import os
from typing import Any

import httpx

LOCAL_LLM_BASE_URL = os.environ.get(
    "LOCAL_LLM_BASE_URL",
    os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
).rstrip("/")
LOCAL_LLM_MODEL = os.environ.get(
    "LOCAL_LLM_MODEL",
    os.environ.get("OLLAMA_MODEL", "gemma4:12b-mlx"),
)
LOCAL_LLM_FALLBACK_MODEL = os.environ.get(
    "LOCAL_LLM_FALLBACK_MODEL",
    os.environ.get("OLLAMA_FALLBACK_MODEL", "ornith:9b"),
)
LOCAL_LLM_NUM_CTX = int(
    os.environ.get("LOCAL_LLM_NUM_CTX", os.environ.get("OLLAMA_NUM_CTX", "8192"))
)
LOCAL_LLM_NUM_PREDICT = int(
    os.environ.get(
        "LOCAL_LLM_NUM_PREDICT", os.environ.get("OLLAMA_NUM_PREDICT", "1024")
    )
)
LOCAL_LLM_KEEP_ALIVE = os.environ.get("LOCAL_LLM_KEEP_ALIVE", "30m")
LOCAL_LLM_TIMEOUT = float(
    os.environ.get(
        "LOCAL_LLM_TIMEOUT_SEC",
        os.environ.get("AGENT_LOCAL_MODEL_TIMEOUT_SEC", "60"),
    )
)

_THINKING_FAMILIES = (
    "ornith",
    "qwen3",
    "qwen3.5",
    "qwen3.6",
    "deepseek-r1",
    "qwq",
    "gemma4",  # thinking optional; we force think off for tool calls
)


def _is_thinking_model(model: str) -> bool:
    m = model.lower()
    return any(f in m for f in _THINKING_FAMILIES)


def _is_local_openai(base_url: str) -> bool:
    provider = os.environ.get("LOCAL_LLM_PROVIDER", "").strip().lower()
    if provider in ("ollama", "openai_compat"):
        return True
    u = base_url.lower()
    return "11434" in u or u.endswith("ollama") or "localhost" in u or "127.0.0.1" in u


class LocalLLM:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
    ) -> None:
        self.base_url = (base_url or LOCAL_LLM_BASE_URL).rstrip("/")
        self.model = model or LOCAL_LLM_MODEL
        self.fallback_model = fallback_model or LOCAL_LLM_FALLBACK_MODEL


async def chat_completion(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    timeout: float | None = None,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    keep_alive: str | None = None,
) -> dict[str, Any]:
    """POST /v1/chat/completions (Ollama OpenAI-compat)."""

    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    local = _is_local_openai(base_url)
    if local:
        payload["options"] = {
            "num_ctx": num_ctx if num_ctx is not None else LOCAL_LLM_NUM_CTX,
            "num_predict": num_predict if num_predict is not None else LOCAL_LLM_NUM_PREDICT,
        }
        payload["keep_alive"] = keep_alive or LOCAL_LLM_KEEP_ALIVE
        if _is_thinking_model(model):
            payload["think"] = False

    resp = await client.post(
        url,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=timeout or LOCAL_LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


async def chat_with_failover(
    client: httpx.AsyncClient,
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
    fallback_model: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.2,
) -> tuple[dict[str, Any], str]:
    """Try primary; on connection/HTTP hard errors only, try fallback.

    Timeouts do NOT failover (swapping models usually makes stalls worse).
    """

    base = (base_url or LOCAL_LLM_BASE_URL).rstrip("/")
    primary = model or LOCAL_LLM_MODEL
    fallback = fallback_model or LOCAL_LLM_FALLBACK_MODEL
    last_err: Exception | None = None

    for candidate in (primary,):
        try:
            data = await chat_completion(
                client,
                base_url=base,
                model=candidate,
                messages=messages,
                tools=tools,
                temperature=temperature,
            )
            return data, f"local:{candidate}"
        except httpx.TimeoutException as exc:
            raise exc
        except Exception as exc:  # noqa: BLE001
            last_err = exc

    if fallback and fallback != primary:
        try:
            data = await chat_completion(
                client,
                base_url=base,
                model=fallback,
                messages=messages,
                tools=tools,
                temperature=temperature,
            )
            return data, f"local:{fallback}"
        except Exception as exc:  # noqa: BLE001
            last_err = exc

    raise RuntimeError(f"No local model available: {last_err}")
