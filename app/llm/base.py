from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Any, Optional, TypedDict, Literal
from dataclasses import dataclass, field


class StreamEvent(TypedDict, total=False):
    """One event emitted from BaseLLMProvider.stream().

    Three event types:
    - {"type": "text", "text": "<delta>"} — partial assistant content
    - {"type": "tool_calls", "tool_calls": [...], "content": Optional[str], "model": str, ...}
      — emitted once when the LLM finishes a turn with tool calls. content is any
      text content the model emitted alongside the tool calls (often None).
    - {"type": "end", "content": str, "model": str, ...} — emitted once when the LLM
      finishes a turn with no tool calls. content is the full accumulated text.
    """
    type: Literal["text", "tool_calls", "end"]
    text: str
    tool_calls: List[Dict[str, Any]]
    content: Optional[str]
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str


@dataclass
class LLMMessage:
    role: str  # user / assistant / tool / system
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None  # tool name for tool result messages


@dataclass
class LLMResponse:
    content: Optional[str]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: str = "stop"


class BaseLLMProvider(ABC):
    provider_name: str

    @abstractmethod
    async def complete(
        self,
        messages: List[LLMMessage],
        model: str,
        system_prompt: Optional[str],
        tools: List[Dict[str, Any]],
        max_tokens: int = 4096,
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[LLMMessage],
        model: str,
        system_prompt: Optional[str],
        tools: List[Dict[str, Any]],
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        pass

    @abstractmethod
    async def health_check(self) -> str:
        pass

    @abstractmethod
    async def list_models(self) -> List[Dict[str, str]]:
        pass
