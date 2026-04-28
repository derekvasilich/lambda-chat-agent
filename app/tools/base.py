from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema for parameters

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }
