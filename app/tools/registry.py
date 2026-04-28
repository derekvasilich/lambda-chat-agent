from typing import Dict, List
from app.tools.base import BaseTool
from app.tools.calculator import CalculatorTool, WebSearchStubTool

_REGISTRY: Dict[str, BaseTool] = {}


def register_tool(tool: BaseTool):
    _REGISTRY[tool.name] = tool


def get_tool(name: str) -> BaseTool | None:
    return _REGISTRY.get(name)


def list_tools() -> List[str]:
    return list(_REGISTRY.keys())


def get_tools_for_conversation(enabled_tools: List[str]) -> List[BaseTool]:
    return [_REGISTRY[name] for name in enabled_tools if name in _REGISTRY]


# Register built-in tools
register_tool(CalculatorTool())
register_tool(WebSearchStubTool())
