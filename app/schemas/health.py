from pydantic import BaseModel
from typing import Dict, Any


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    database: str
    llm_providers: Dict[str, str]
