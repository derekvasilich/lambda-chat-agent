import json
from typing import AsyncIterator, List, Dict, Any, Optional
import anthropic as anthropic_sdk
from app.llm.base import BaseLLMProvider, LLMMessage, LLMResponse
from app.config import settings

class AnthropicProvider(BaseLLMProvider):
    provider_name = "anthropic"

    def __init__(self):
        self._client = anthropic_sdk.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    def _build_messages(self, messages: List[LLMMessage]) -> list:
        result = []
        for msg in messages:
            if msg.role == "system":
                continue  # Anthropic takes system prompt separately
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
    ) -> AsyncIterator[str]:
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            messages=self._build_messages(messages),
        )
        if system_prompt:
            kwargs["system"] = system_prompt

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def health_check(self) -> str:
        if not settings.ANTHROPIC_API_KEY:
            return "unconfigured"
        try:
            await self._client.models.list()
            return "ok"
        except Exception as e:
            return f"error: {e}"

    async def list_models(self) -> List[Dict[str, str]]:
        try:
            models = []
            response = await self._client.models.list()
            for model in response.data:
                models.append({"id": model.id, "name": model.display_name})
            return models
        except Exception:
            return [
                {"id": "claude-opus-4-7", "name": "Claude Opus 4.7"},
                {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6"},
                {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
            ]
