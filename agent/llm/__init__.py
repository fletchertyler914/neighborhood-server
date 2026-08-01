"""OpenAI-compatible LocalLLM client (host Ollama / MLX by default)."""

from agent.llm.client import LocalLLM, chat_completion

__all__ = ["LocalLLM", "chat_completion"]
