import uuid
from datetime import datetime, timezone
from typing import Optional, List, Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Conversation(BaseModel):
    id: str = Field(default_factory=new_uuid)
    user_id: str
    title: str = "New Conversation"
    system_prompt: Optional[str] = None
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    max_history_messages: Optional[int] = None
    enabled_tools: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Message(BaseModel):
    id: str = Field(default_factory=new_uuid)
    conversation_id: str
    sort_key: str = ""
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[Any]] = None
    tool_call_id: Optional[str] = None
    model_used: Optional[str] = None
    token_count: Optional[int] = None
    created_at: datetime = Field(default_factory=utcnow)
