from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.db import Conversation
from app.schemas.config import ConversationConfigResponse, ConversationConfigUpdate
from app.auth import get_current_user, UserClaims
from app.routers.conversations import _get_owned_conversation

router = APIRouter()


@router.get(
    "/conversations/{conversation_id}/config",
    response_model=ConversationConfigResponse,
    summary="Get conversation config",
    tags=["Config"],
)
async def get_config(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserClaims = Depends(get_current_user),
):
    conv = await _get_owned_conversation(conversation_id, user.sub, db)
    return ConversationConfigResponse(
        conversation_id=conv.id,
        system_prompt=conv.system_prompt,
        provider=conv.provider,
        model=conv.model,
        max_history_messages=conv.max_history_messages,
        enabled_tools=conv.enabled_tools or [],
    )


@router.patch(
    "/conversations/{conversation_id}/config",
    response_model=ConversationConfigResponse,
    summary="Update conversation config",
    tags=["Config"],
)
async def update_config(
    conversation_id: str,
    body: ConversationConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserClaims = Depends(get_current_user),
):
    conv = await _get_owned_conversation(conversation_id, user.sub, db)

    if body.system_prompt is not None:
        conv.system_prompt = body.system_prompt
    if body.provider is not None:
        conv.provider = body.provider
    if body.model is not None:
        conv.model = body.model
    if body.max_history_messages is not None:
        conv.max_history_messages = body.max_history_messages
    if body.enabled_tools is not None:
        conv.enabled_tools = body.enabled_tools

    await db.commit()
    await db.refresh(conv)

    return ConversationConfigResponse(
        conversation_id=conv.id,
        system_prompt=conv.system_prompt,
        provider=conv.provider,
        model=conv.model,
        max_history_messages=conv.max_history_messages,
        enabled_tools=conv.enabled_tools or [],
    )
