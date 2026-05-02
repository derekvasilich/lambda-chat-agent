from typing import AsyncIterator, List, Dict, Any, Optional
import openai as openai_sdk
from app.llm.base import BaseLLMProvider, LLMMessage, LLMResponse
from app.config import settings


class OpenAIProvider(BaseLLMProvider):
    provider_name = "openai"

    _CHAT_MODEL_PREFIXES = ("gpt-", "o1", "o3", "o4")

    def __init__(
            self,
            api_key: Optional[str] = None,
            base_url: Optional[str] = None,
            provider_name: str = "openai"
        ):
        self.provider_name = provider_name
        self._client = openai_sdk.AsyncOpenAI(
            api_key=api_key or settings.OPENAI_API_KEY,
            base_url=base_url or None,
        )

    def _build_messages(self, messages: List[LLMMessage], system_prompt: Optional[str]) -> list:
        result = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        for msg in messages:
            if msg.role == "system":
                continue
            if msg.role == "tool":
                result.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content or "",
                })
            elif msg.tool_calls:
                result.append({
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": msg.tool_calls,
                })
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
            messages=self._build_messages(messages, system_prompt),
            max_tokens=max_tokens,
        )
        if tools:
            kwargs["tools"] = tools

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]

        return LLMResponse(
            content=msg.content,
            model=response.model,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
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
            messages=self._build_messages(messages, system_prompt),
            max_tokens=max_tokens,
            stream=True,
        )

        async for chunk in await self._client.chat.completions.create(**kwargs):
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def health_check(self) -> str:
        if not (self._client.api_key or settings.OPENAI_API_KEY):
            return "unconfigured"
        try:
            await self._client.models.list()
            return "ok"
        except Exception as e:
            return f"error: {e}"

    async def list_models(self) -> List[Dict[str, str]]:
        if not (self._client.api_key or settings.OPENAI_API_KEY):
            return []
        if self.provider_name == "custom":
            return [{
                "id": settings.CUSTOM_LLM_MODEL, 
                "name": f"Custom: {settings.CUSTOM_LLM_MODEL}"
            }]
        try:
            response = await self._client.models.list()
            return [
                {
                    "id": model.id,
                    "name": model.id.replace('-', ' ').title(),
                }
                for model in response.data
                if model.id.startswith(self._CHAT_MODEL_PREFIXES)
            ]
        except Exception:
            return []
