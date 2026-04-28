from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Any


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000, examples=["What is the capital of France?"])

    model_config = {"json_schema_extra": {"example": {"content": "What is the capital of France?"}}}


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: Optional[str]
    tool_calls: Optional[List[Any]]
    tool_call_id: Optional[str]
    model_used: Optional[str]
    token_count: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    items: List[MessageResponse]
    has_more: bool
    next_cursor: Optional[str]
