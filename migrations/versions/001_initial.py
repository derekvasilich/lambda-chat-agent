"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(256), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False, server_default="New Conversation"),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("provider", sa.String(64), nullable=False, server_default="anthropic"),
        sa.Column("model", sa.String(128), nullable=False, server_default="claude-sonnet-4-6"),
        sa.Column("max_history_messages", sa.Integer, nullable=True),
        sa.Column("enabled_tools", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False, index=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("tool_calls", sa.JSON, nullable=True),
        sa.Column("tool_call_id", sa.String(128), nullable=True),
        sa.Column("model_used", sa.String(128), nullable=True),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
