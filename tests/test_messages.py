import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.llm.base import LLMResponse


def make_mock_provider(content="Paris is the capital of France.", tool_calls=None):
    mock_provider = MagicMock()
    mock_provider.complete = AsyncMock(return_value=LLMResponse(
        content=content,
        model="mock-model",
        input_tokens=10,
        output_tokens=20,
        tool_calls=tool_calls,
    ))
    return mock_provider


@pytest.mark.asyncio
async def test_send_message(client, conversation):
    conv_id = conversation["id"]
    with patch("app.routers.messages.get_provider", return_value=make_mock_provider()):
        resp = await client.post(f"/v1/conversations/{conv_id}/messages", json={"content": "What is the capital of France?"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["role"] == "assistant"
    assert "Paris" in data["content"]


@pytest.mark.asyncio
async def test_message_content_too_long(client, conversation):
    conv_id = conversation["id"]
    resp = await client.post(f"/v1/conversations/{conv_id}/messages", json={"content": "x" * 1001})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_message_empty_content(client, conversation):
    conv_id = conversation["id"]
    resp = await client.post(f"/v1/conversations/{conv_id}/messages", json={"content": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_send_message_not_found(client):
    resp = await client.post("/v1/conversations/no-such-conv/messages", json={"content": "hello"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_messages(client, conversation):
    conv_id = conversation["id"]
    with patch("app.routers.messages.get_provider", return_value=make_mock_provider()):
        await client.post(f"/v1/conversations/{conv_id}/messages", json={"content": "Hello"})
    resp = await client.get(f"/v1/conversations/{conv_id}/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2  # user + assistant
    assert data["items"][0]["role"] == "assistant"
    assert data["items"][1]["role"] == "user"


@pytest.mark.asyncio
async def test_clear_messages(client, conversation):
    conv_id = conversation["id"]
    with patch("app.routers.messages.get_provider", return_value=make_mock_provider()):
        await client.post(f"/v1/conversations/{conv_id}/messages", json={"content": "Hello"})
    resp = await client.delete(f"/v1/conversations/{conv_id}/messages")
    assert resp.status_code == 204
    resp = await client.get(f"/v1/conversations/{conv_id}/messages")
    assert len(resp.json()["items"]) == 0


@pytest.mark.asyncio
async def test_auth_required_messages(unauth_client):
    resp = await unauth_client.post("/v1/conversations/any-id/messages", json={"content": "hi"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_tool_call_loop(client, conversation):
    conv_id = conversation["id"]
    tool_call_response = LLMResponse(
        content=None,
        model="mock-model",
        input_tokens=10,
        output_tokens=5,
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "calculator", "arguments": '{"expression": "2+2"}'},
        }],
    )
    final_response = LLMResponse(
        content="The answer is 4.",
        model="mock-model",
        input_tokens=15,
        output_tokens=10,
    )
    mock_provider = MagicMock()
    mock_provider.complete = AsyncMock(side_effect=[tool_call_response, final_response])

    with patch("app.routers.messages.get_provider", return_value=mock_provider):
        resp = await client.post(f"/v1/conversations/{conv_id}/messages", json={"content": "What is 2+2?"})

    assert resp.status_code == 201
    assert resp.json()["content"] == "The answer is 4."
    assert mock_provider.complete.call_count == 2
