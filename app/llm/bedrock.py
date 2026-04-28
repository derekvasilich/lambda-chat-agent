from typing import List, Dict
import asyncio
import boto3
import anthropic as anthropic_sdk
from app.llm.base import BaseLLMProvider
from app.config import settings

class BedrockProvider(BaseLLMProvider):
    provider_name = "bedrock"

    def __init__(self):
        # Uses boto3 credentials automatically (Lambda IAM role)
        self._client = anthropic_sdk.AnthropicBedrock()

    async def complete(self, messages, model, system=None, tools=None, **kwargs):
        response = self._client.messages.create(
            model=model,
            max_tokens=kwargs.get("max_tokens", 4096),
            messages=messages,
            system=system or "",
            tools=tools or [],
        )
        return response

    async def stream(self, messages, model, system=None, tools=None, **kwargs):
        with self._client.messages.stream(
            model=model,
            max_tokens=kwargs.get("max_tokens", 4096),
            messages=messages,
            system=system or [],
            tools=tools or [],
        ) as stream:
            for text in stream.text_stream:
                yield text

    async def health_check(self) -> str:
        if not self._client.api_key:
            return "unconfigured"
        try:
            await self._client.platform_headers()
            return "ok"
        except Exception as e:
            return f"error: {e}"

    async def list_models(self) -> List[Dict[str, str]]:
        try:
            def _fetch():
                client = boto3.client("bedrock")
                response = client.list_foundation_models(
                    byOutputModality="TEXT",
                    byInferenceType="ON_DEMAND",
                )
                return [
                    {
                        "id": m.modelId,
                        "name": f"{m.providerName} {m.modelName}",
                    }
                    for m in response["modelSummaries"]
                    if "TEXT" in m.get("inputModalities", [])
                ]

            return await asyncio.get_event_loop().run_in_executor(None, _fetch)
        except Exception:
            return [
                {"id": "anthropic.claude-opus-4-7", "name": "Anthropic Claude Opus 4.7"},
                {"id": "anthropic.claude-sonnet-4-6", "name": "Anthropic Claude Sonnet 4.6"},
                {"id": "anthropic.claude-haiku-4-5-20251001", "name": "Anthropic Claude Haiku 4.5"},
            ]