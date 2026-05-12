from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Operation:
    spec_id: str
    op_id: str
    method: str
    path_template: str
    summary: str
    description: str
    param_schema: Dict[str, Any]
    security: List[Dict[str, Any]] = field(default_factory=list)
    servers: List[str] = field(default_factory=list)

    def embedding_text(self) -> str:
        parts = [
            self.method.upper(),
            self.path_template,
            self.summary or "",
            self.description or "",
        ]
        return " ".join(p for p in parts if p)

    def slim_view(self) -> Dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "operation_id": self.op_id,
            "method": self.method.upper(),
            "path": self.path_template,
            "summary": self.summary or self.description[:120] if self.description else "",
        }
