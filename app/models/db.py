import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def new_uuid():
    return str(uuid.uuid4())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), default="New Conversation")
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), default="anthropic")
    model: Mapped[str] = mapped_column(String(128), default="claude-sonnet-4-6")
    max_history_messages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled_tools: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", lazy="select"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user / assistant / tool
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
