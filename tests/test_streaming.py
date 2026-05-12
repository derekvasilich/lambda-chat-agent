import json
from unittest.mock import MagicMock, patch

import pytest


def _make_stream_provider(events_per_call):
    """events_per_call: list of event-lists; each inner list is a single stream() call's events."""

    call_iter = iter(events_per_call)

    def stream(*args, **kwargs):
        events = next(call_iter)

        async def gen():
            for e in events:
                yield e

        return gen()

    provider = MagicMock()
    provider.stream = stream
    return provider


def _parse_sse(body: str):
    """Parse SSE response body into a list of payloads (dicts or '[DONE]')."""
    events = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        if payload == "[DONE]":
            events.append("[DONE]")
        else:
            events.append(json.loads(payload))
    return events


@pytest.mark.asyncio
async def test_stream_text_only(client, conversation):
    conv_id = conversation["id"]
    events = [
        {"type": "text", "text": "Hello "},
        {"type": "text", "text": "world."},
        {"type": "end", "content": "Hello world.", "model": "mock",
         "input_tokens": 5, "output_tokens": 2, "finish_reason": "stop"},
    ]
    provider = _make_stream_provider([events])

    with patch("app.routers.messages.get_provider", return_value=provider):
        resp = await client.post(
            f"/v1/conversations/{conv_id}/messages?stream=true",
            json={"content": "Hi"},
        )

    assert resp.status_code == 200
    parsed = _parse_sse(resp.text)
    texts = [e["content"] for e in parsed if isinstance(e, dict) and "content" in e]
    assert texts == ["Hello ", "world."]
    assert parsed[-1] == "[DONE]"


@pytest.mark.asyncio
async def test_stream_persists_final_assistant_message(client, conversation):
    conv_id = conversation["id"]
    events = [
        {"type": "text", "text": "ok"},
        {"type": "end", "content": "ok", "model": "mock",
         "input_tokens": 1, "output_tokens": 1, "finish_reason": "stop"},
    ]
    provider = _make_stream_provider([events])

    with patch("app.routers.messages.get_provider", return_value=provider):
        await client.post(
            f"/v1/conversations/{conv_id}/messages?stream=true",
            json={"content": "test"},
        )

    history = await client.get(f"/v1/conversations/{conv_id}/messages")
    items = history.json()["items"]
    # Newest first per existing convention; should include the user message and assistant
    roles = [m["role"] for m in items]
    assert "assistant" in roles
    assistant_msg = next(m for m in items if m["role"] == "assistant")
    assert assistant_msg["content"] == "ok"


@pytest.mark.asyncio
async def test_stream_with_tool_call_loop(client, conversation):
    conv_id = conversation["id"]
    # First stream call: model emits a tool call
    first_call = [
        {
            "type": "tool_calls",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "calculator", "arguments": '{"expression": "2+2"}'},
            }],
            "content": None,
            "model": "mock",
            "input_tokens": 10,
            "output_tokens": 5,
            "finish_reason": "tool_calls",
        },
    ]
    # Second stream call: model emits final text after tool result
    second_call = [
        {"type": "text", "text": "Result is 4."},
        {"type": "end", "content": "Result is 4.", "model": "mock",
         "input_tokens": 15, "output_tokens": 5, "finish_reason": "stop"},
    ]
    provider = _make_stream_provider([first_call, second_call])

    # Enable calculator on the conversation first
    await client.patch(f"/v1/conversations/{conv_id}/config", json={
        "enabled_tools": ["calculator"],
    })

    with patch("app.routers.messages.get_provider", return_value=provider):
        resp = await client.post(
            f"/v1/conversations/{conv_id}/messages?stream=true",
            json={"content": "What is 2+2?"},
        )

    assert resp.status_code == 200
    parsed = _parse_sse(resp.text)

    # Should see a tool_call event then tool_result then text deltas then [DONE]
    types_seen = []
    for e in parsed:
        if e == "[DONE]":
            types_seen.append("DONE")
        elif "tool_call" in e:
            types_seen.append("tool_call")
        elif "tool_result" in e:
            types_seen.append("tool_result")
        elif "content" in e:
            types_seen.append("content")

    assert "tool_call" in types_seen
    assert "tool_result" in types_seen
    assert types_seen[-1] == "DONE"
    # Final text content delivered to client
    assert "content" in types_seen
    # tool_call should come before tool_result, both before final content
    assert types_seen.index("tool_call") < types_seen.index("tool_result")
    assert types_seen.index("tool_result") < types_seen.index("content")


@pytest.mark.asyncio
async def test_stream_with_tool_call_persists_full_turn(client, conversation):
    conv_id = conversation["id"]
    first_call = [
        {
            "type": "tool_calls",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "calculator", "arguments": '{"expression": "3*3"}'},
            }],
            "content": None,
            "model": "mock",
            "input_tokens": 10,
            "output_tokens": 5,
            "finish_reason": "tool_calls",
        },
    ]
    second_call = [
        {"type": "end", "content": "Nine.", "model": "mock",
         "input_tokens": 15, "output_tokens": 2, "finish_reason": "stop"},
    ]
    provider = _make_stream_provider([first_call, second_call])

    await client.patch(f"/v1/conversations/{conv_id}/config", json={
        "enabled_tools": ["calculator"],
    })

    with patch("app.routers.messages.get_provider", return_value=provider):
        await client.post(
            f"/v1/conversations/{conv_id}/messages?stream=true",
            json={"content": "What is 3*3?"},
        )

    history = await client.get(f"/v1/conversations/{conv_id}/messages")
    roles = [m["role"] for m in history.json()["items"]]
    # Expect: user msg, assistant w/ tool_calls, tool result, final assistant
    assert roles.count("assistant") == 2
    assert roles.count("tool") == 1
    assert roles.count("user") == 1
