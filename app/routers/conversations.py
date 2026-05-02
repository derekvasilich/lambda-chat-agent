from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dynamodb import get_conversations_table, get_messages_table
from app.repositories.conversations import ConversationRepository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationListResponse,
)
from app.auth import get_current_user, UserClaims

router = APIRouter()


async def get_conv_repo(
    conv_table=Depends(get_conversations_table),
    msg_table=Depends(get_messages_table),
) -> ConversationRepository:
    return ConversationRepository(conv_table, msg_table)


async def _get_owned_conversation(
    conversation_id: str, user_id: str, repo: ConversationRepository
) -> ConversationResponse:
    conv = await repo.get(conversation_id, user_id)
    if not conv:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Conversation not found", "details": {}}},
        )
    return conv


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="List conversations",
    tags=["Conversations"],
)
async def list_conversations(
    page_size: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    repo: ConversationRepository = Depends(get_conv_repo),
    user: UserClaims = Depends(get_current_user),
):
    convs, next_cursor = await repo.list(user.sub, page_size, cursor)
    return ConversationListResponse(items=convs, next_cursor=next_cursor)


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=201,
    summary="Create conversation",
    tags=["Conversations"],
)
async def create_conversation(
    body: ConversationCreate,
    repo: ConversationRepository = Depends(get_conv_repo),
    user: UserClaims = Depends(get_current_user),
):
    return await repo.create(user.sub, body)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    summary="Delete conversation",
    tags=["Conversations"],
)
async def delete_conversation(
    conversation_id: str,
    repo: ConversationRepository = Depends(get_conv_repo),
    user: UserClaims = Depends(get_current_user),
):
    deleted = await repo.delete(conversation_id, user.sub)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Conversation not found", "details": {}}},
        )
