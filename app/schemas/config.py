from pydantic import BaseModel, Field
from typing import Optional, List


class ConversationConfigResponse(BaseModel):
    conversation_id: str
    system_prompt: Optional[str]
    provider: str
    model: str
    max_history_messages: Optional[int]
    enabled_tools: List[str]


class ConversationConfigUpdate(BaseModel):
    system_prompt: Optional[str] = Field(default=None, examples=["You are a pirate."])
    provider: Optional[str] = Field(default=None, examples=["openai"])
    model: Optional[str] = Field(default=None, examples=["gpt-4o"])
    max_history_messages: Optional[int] = Field(default=None, ge=1, le=500, examples=[50])
    enabled_tools: Optional[List[str]] = Field(default=None, examples=[["calculator"]])

    model_config = {"json_schema_extra": {"example": {
        "model": "gpt-4o",
        "provider": "openai",
        "enabled_tools": ["calculator"],
    }}}
