from typing import Dict
from app.llm.base import BaseLLMProvider
from app.config import settings

from app.llm.anthropic import AnthropicProvider
from app.llm.openai import OpenAIProvider
from app.llm.bedrock import BedrockProvider

_providers: Dict[str, BaseLLMProvider] = {}

def _init_providers():
    _providers["anthropic"] = AnthropicProvider()
    _providers["openai"] = OpenAIProvider(api_key=settings.OPENAI_API_KEY)
    _providers["bedrock"] = BedrockProvider()
    if settings.CUSTOM_LLM_BASE_URL:
        _providers["custom"] = OpenAIProvider(
            api_key=settings.CUSTOM_LLM_API_KEY,
            base_url=settings.CUSTOM_LLM_BASE_URL,
            provider_name="custom",
        )


def get_provider(name: str) -> BaseLLMProvider:
    if not _providers:
        _init_providers()
    if name not in _providers:
        raise ValueError(f"Unknown LLM provider: {name}")
    return _providers[name]


def list_providers() -> Dict[str, BaseLLMProvider]:
    if not _providers:
        _init_providers()
    return dict(_providers)
