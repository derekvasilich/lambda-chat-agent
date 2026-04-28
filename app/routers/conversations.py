from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, and_
from app.database import get_db
from app.models.db import Conversation, Message
from app.schemas.conversation import ConversationCreate, ConversationResponse, ConversationListResponse, FirstMessageResponse
from app.auth import get_current_user, UserClaims
from app.config import settings

router = APIRouter()


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="List conversations",
    tags=["Conversations"],
)
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: UserClaims = Depends(get_current_user),
):
    offset = (page - 1) * page_size
    total_result = await db.execute(
        select(func.count()).where(Conversation.user_id == user.sub)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.sub)
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    conversations = result.scalars().all()

    conv_ids = [c.id for c in conversations]
    first_messages: dict[str, Message] = {}
    if conv_ids:
        min_subq = (
            select(Message.conversation_id, func.min(Message.created_at).label("min_created"))
            .where(Message.conversation_id.in_(conv_ids))
            .group_by(Message.conversation_id)
            .subquery()
        )
        msgs_result = await db.execute(
            select(Message).join(
                min_subq,
                and_(
                    Message.conversation_id == min_subq.c.conversation_id,
                    Message.created_at == min_subq.c.min_created,
                ),
            )
        )
        for msg in msgs_result.scalars().all():
            first_messages.setdefault(msg.conversation_id, msg)

    items = []
    for c in conversations:
        data = ConversationResponse.model_validate(c)
        msg = first_messages.get(c.id)
        data.first_message = FirstMessageResponse.model_validate(msg) if msg else None
        items.append(data)

    return ConversationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=201,
    summary="Create conversation",
    tags=["Conversations"],
)
async def create_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: UserClaims = Depends(get_current_user),
):
    conv = Conversation(
        user_id=user.sub,
        title=body.title,
        system_prompt=body.system_prompt or settings.DEFAULT_SYSTEM_PROMPT,
        provider=body.provider or settings.DEFAULT_LLM_PROVIDER,
        model=body.model or settings.DEFAULT_MODEL,
        enabled_tools=[],
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationResponse.model_validate(conv)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    summary="Delete conversation",
    tags=["Conversations"],
)
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserClaims = Depends(get_current_user),
):
    conv = await _get_owned_conversation(conversation_id, user.sub, db)
    await db.delete(conv)
    await db.commit()


async def _get_owned_conversation(conversation_id: str, user_id: str, db: AsyncSession) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Conversation not found", "details": {}}},
        )
    return conv
