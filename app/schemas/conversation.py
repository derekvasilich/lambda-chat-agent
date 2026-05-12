from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class ConversationCreate(BaseModel):
    title: str = Field(default="New Conversation", max_length=255, examples=["My first chat"])
    system_prompt: Optional[str] = Field(default=None, examples=["You are a helpful assistant."])
    provider: Optional[str] = Field(default=None, examples=["openai"])
    model: Optional[str] = Field(default=None, examples=["gpt-4o"])

    model_config = {"json_schema_extra": {"example": {
        "title": "My Research Chat",
        "system_prompt": "You are a research assistant.",
        "provider": "openai",
        "model": "gpt-4o",
    }}}


class FirstMessageResponse(BaseModel):
    id: str
    role: str
    content: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: str
    system_prompt: Optional[str]
    provider: str
    model: str
    max_history_messages: Optional[int] = None
    enabled_tools: List[str]
    enabled_specs: List[str] = []
    created_at: datetime
    updated_at: datetime
    first_message: Optional[FirstMessageResponse] = None


class ConversationListResponse(BaseModel):
    items: List[ConversationResponse]
    next_cursor: Optional[str] = None
