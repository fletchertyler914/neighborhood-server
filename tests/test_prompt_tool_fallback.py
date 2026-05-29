"""Prompt-mode tool-call fallback for models Ollama refuses to send tools to."""

from __future__ import annotations

from agent.orchestrator.app import (
    _extract_prompt_tool_call,
    _model_lacks_native_tools,
    _summarize_tool_schemas,
    _wrap_prompt_tool_call,
)


def test_model_lacks_native_tools_detects_deepseek_variants():
    assert _model_lacks_native_tools("deepseek-r1:8b")
    assert _model_lacks_native_tools("deepseek-r1:8b-llama-distill-q4_K_M")
    assert _model_lacks_native_tools("ollama:deepseek-r1:8b")
    assert not _model_lacks_native_tools("qwen2.5:7b-instruct")
    assert not _model_lacks_native_tools("qwen3:8b")
    assert not _model_lacks_native_tools("llama3.1:8b")


def test_summarize_tool_schemas_renders_callable_signatures():
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "say",
                "description": "Broadcast a chat message",
                "parameters": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            },
        }
    ]
    text = _summarize_tool_schemas(schemas)
    assert "say(message*:string)" in text
    assert "Broadcast a chat message" in text


def test_extract_prompt_tool_call_parses_clean_json():
    text = '{"tool": "say", "arguments": {"message": "hello"}}'
    call = _extract_prompt_tool_call(text)
    assert call == {"name": "say", "arguments": {"message": "hello"}}


def test_extract_prompt_tool_call_strips_think_block_and_fences():
    text = (
        "<think>I should say hello to the players.</think>\n"
        "```json\n"
        '{"tool": "say", "arguments": {"message": "hi"}}\n'
        "```\n"
    )
    call = _extract_prompt_tool_call(text)
    assert call == {"name": "say", "arguments": {"message": "hi"}}


def test_extract_prompt_tool_call_finds_embedded_object_in_prose():
    text = (
        "Sure, here is the call:\n"
        '{"tool": "set_time", "arguments": {"value": "day"}}\n'
        "Let me know if anything else is needed."
    )
    call = _extract_prompt_tool_call(text)
    assert call == {"name": "set_time", "arguments": {"value": "day"}}


def test_extract_prompt_tool_call_returns_none_on_garbage():
    assert _extract_prompt_tool_call("") is None
    assert _extract_prompt_tool_call("just some prose, no JSON here") is None
    # Object exists but lacks a tool name field.
    assert _extract_prompt_tool_call('{"foo": "bar"}') is None


def test_wrap_prompt_tool_call_shapes_an_openai_choice():
    wrapped = _wrap_prompt_tool_call(
        {"name": "say", "arguments": {"message": "hi"}},
        "{\"tool\": \"say\", \"arguments\": {\"message\": \"hi\"}}",
    )
    msg = wrapped["choices"][0]["message"]
    assert msg["role"] == "assistant"
    assert msg["tool_calls"][0]["function"]["name"] == "say"
    assert msg["tool_calls"][0]["function"]["arguments"] == '{"message": "hi"}'


def test_wrap_prompt_tool_call_no_call_keeps_raw_content():
    wrapped = _wrap_prompt_tool_call(None, "I'm not sure what to do.")
    msg = wrapped["choices"][0]["message"]
    assert "tool_calls" not in msg
    assert msg["content"] == "I'm not sure what to do."
