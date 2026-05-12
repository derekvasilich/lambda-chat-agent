from typing import AsyncIterator, List, Dict, Any, Optional
import openai as openai_sdk
from app.llm.base import BaseLLMProvider, LLMMessage, LLMResponse, StreamEvent
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
    ) -> AsyncIterator[StreamEvent]:
        kwargs: dict = dict(
            model=model,
            messages=self._build_messages(messages, system_prompt),
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        if tools:
            kwargs["tools"] = tools

        tool_calls_buffer: Dict[int, Dict[str, Any]] = {}
        text_buffer: List[str] = []
        finish_reason: Optional[str] = None
        input_tokens = 0
        output_tokens = 0
        model_used = model

        async for chunk in await self._client.chat.completions.create(**kwargs):
            if chunk.usage:
                input_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0
            model_used = chunk.model or model_used
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta and delta.content:
                text_buffer.append(delta.content)
                yield {"type": "text", "text": delta.content}

            if delta and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    buf = tool_calls_buffer.setdefault(idx, {
                        "id": None,
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    })
                    if tc_delta.id:
                        buf["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            buf["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            buf["function"]["arguments"] += tc_delta.function.arguments

            if choice.finish_reason:
                finish_reason = choice.finish_reason

        text_content = "".join(text_buffer) if text_buffer else None
        if tool_calls_buffer:
            tool_calls = [tool_calls_buffer[i] for i in sorted(tool_calls_buffer)]
            yield {
                "type": "tool_calls",
                "tool_calls": tool_calls,
                "content": text_content,
                "model": model_used,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "finish_reason": finish_reason or "tool_calls",
            }
        else:
            yield {
                "type": "end",
                "content": text_content or "",
                "model": model_used,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "finish_reason": finish_reason or "stop",
            }

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
