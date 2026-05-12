import asyncio
import json
from typing import AsyncIterator, List, Dict, Any, Optional
import aioboto3
import botocore.config
import anthropic as anthropic_sdk
from app.llm.base import BaseLLMProvider, LLMMessage, LLMResponse, StreamEvent
from app.config import settings

class BedrockProvider(BaseLLMProvider):
    provider_name = "bedrock"

    def __init__(self):
        self._client = anthropic_sdk.AsyncAnthropicBedrock()

    def _build_messages(self, messages: List[LLMMessage]) -> list:
        result = []
        for msg in messages:
            if msg.role == "system":
                continue
            if msg.role == "tool":
                result.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content or "",
                    }],
                })
            elif msg.tool_calls:
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                    })
                result.append({"role": "assistant", "content": content})
            else:
                result.append({"role": msg.role, "content": msg.content or ""})
        return result

    async def complete(
        self,
        messages: List[LLMMessage],
        model: str,
        system_prompt: Optional[str],
        tools: List[Dict[str, Any]],
        max_tokens: int = 4096,
    ) -> LLMResponse:
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            messages=self._build_messages(messages),
        )
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        tool_calls = None
        text_content = None
        for block in response.content:
            if block.type == "text":
                text_content = block.text
            elif block.type == "tool_use":
                tool_calls = tool_calls or []
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {"name": block.name, "arguments": json.dumps(block.input)},
                })

        return LLMResponse(
            content=text_content,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "stop",
        )

    async def stream(
        self,
        messages: List[LLMMessage],
        model: str,
        system_prompt: Optional[str],
        tools: List[Dict[str, Any]],
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            messages=self._build_messages(messages),
        )
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield {"type": "text", "text": text}

            final = await stream.get_final_message()

        text_content: Optional[str] = None
        tool_calls: List[Dict[str, Any]] = []
        for block in final.content:
            if block.type == "text":
                text_content = (text_content or "") + block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {"name": block.name, "arguments": json.dumps(block.input)},
                })

        usage = getattr(final, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "output_tokens", 0) if usage else 0
        model_used = getattr(final, "model", model)
        finish_reason = getattr(final, "stop_reason", None) or "stop"

        if tool_calls:
            yield {
                "type": "tool_calls",
                "tool_calls": tool_calls,
                "content": text_content,
                "model": model_used,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "finish_reason": finish_reason,
            }
        else:
            yield {
                "type": "end",
                "content": text_content or "",
                "model": model_used,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "finish_reason": finish_reason,
            }

    async def health_check(self) -> str:
        if settings.DEFAULT_LLM_PROVIDER != 'bedrock':
            return "unconfigured"
        try:
            config = botocore.config.Config(
                connect_timeout=3,
                read_timeout=5,
                retries={"max_attempts": 1}
            )
            session = aioboto3.Session()
            async with session.client("bedrock", config=config) as client:
                await asyncio.wait_for(client.list_foundation_models(), timeout=5.0)
            return "ok"
        except asyncio.TimeoutError:
            return "error: timeout"
        except Exception as e:
            return f"error: {e}"

    async def list_models(self) -> List[Dict[str, str]]:
        if settings.DEFAULT_LLM_PROVIDER != 'bedrock':
            return []
        try:
            session = aioboto3.Session()
            async with session.client("bedrock") as client:
                response = await client.list_foundation_models(
                    byOutputModality="TEXT",
                    byInferenceType="ON_DEMAND",
                )
            return [
                {
                    "id": m["modelId"],
                    "name": f"{m['providerName']} {m['modelName']}",
                }
                for m in response["modelSummaries"]
                if "TEXT" in m.get("inputModalities", [])
            ]
        except Exception:
            return []