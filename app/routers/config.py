from fastapi import APIRouter, Depends, HTTPException

from app.routers.conversations import get_conv_repo, _get_owned_conversation
from app.repositories.conversations import ConversationRepository
from app.schemas.config import ConversationConfigResponse, ConversationConfigUpdate
from app.auth import get_current_user, UserClaims

router = APIRouter()


@router.get(
    "/conversations/{conversation_id}/config",
    response_model=ConversationConfigResponse,
    summary="Get conversation config",
    tags=["Config"],
)
async def get_config(
    conversation_id: str,
    repo: ConversationRepository = Depends(get_conv_repo),
    user: UserClaims = Depends(get_current_user),
):
    conv = await _get_owned_conversation(conversation_id, user.sub, repo)
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
    repo: ConversationRepository = Depends(get_conv_repo),
    user: UserClaims = Depends(get_current_user),
):
    conv = await repo.update_config(conversation_id, user.sub, body)
    if conv is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Conversation not found", "details": {}}},
        )
    return ConversationConfigResponse(
        conversation_id=conv.id,
        system_prompt=conv.system_prompt,
        provider=conv.provider,
        model=conv.model,
        max_history_messages=conv.max_history_messages,
        enabled_tools=conv.enabled_tools or [],
    )
