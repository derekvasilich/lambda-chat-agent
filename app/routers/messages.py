import json
from typing import Optional, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.dynamodb import get_conversations_table, get_messages_table, get_dynamodb_resource
from app.repositories.conversations import ConversationRepository
from app.repositories.messages import MessageRepository
from app.routers.conversations import get_conv_repo, _get_owned_conversation
from app.schemas.message import SendMessageRequest, MessageResponse, MessageListResponse
from app.auth import get_current_user, UserClaims
from app.llm import get_provider, LLMMessage
from app.tools.registry import get_tools_for_conversation, get_tool
from app.middleware.rate_limit import limiter, rate_limit_string
from app.config import settings
import structlog

logger = structlog.get_logger()
router = APIRouter()


async def get_msg_repo(msg_table=Depends(get_messages_table)) -> MessageRepository:
    return MessageRepository(msg_table)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="List messages",
    tags=["Chat"],
)
async def list_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = Query(None, description="Cursor: encode of last seen sort_key"),
    conv_repo: ConversationRepository = Depends(get_conv_repo),
    msg_repo: MessageRepository = Depends(get_msg_repo),
    user: UserClaims = Depends(get_current_user),
):
    await _get_owned_conversation(conversation_id, user.sub, conv_repo)

    items, has_more, next_cursor = await msg_repo.list(conversation_id, limit, before)
    return MessageListResponse(items=items, has_more=has_more, next_cursor=next_cursor)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=201,
    summary="Send message",
    tags=["Chat"],
)
@limiter.limit(rate_limit_string)
async def send_message(
    request: Request,
    conversation_id: str,
    body: SendMessageRequest,
    stream: bool = Query(False),
    conv_repo: ConversationRepository = Depends(get_conv_repo),
    msg_repo: MessageRepository = Depends(get_msg_repo),
    user: UserClaims = Depends(get_current_user),
):
    conv = await _get_owned_conversation(conversation_id, user.sub, conv_repo)
    request.state.user = user

    await msg_repo.add(conv.id, "user", content=body.content)

    if conv.title == "New Conversation" and body.content:
        title = body.content.replace("\n", " ").strip()[:100]
        await conv_repo.set_title(conv.id, title)

    max_msgs = conv.max_history_messages or settings.MAX_HISTORY_MESSAGES
    llm_messages = await msg_repo.get_history(conv.id, max_msgs)

    provider = get_provider(conv.provider)
    tools_list = get_tools_for_conversation(conv.enabled_tools or [])
    tool_schemas = [
        t.to_anthropic_schema() if conv.provider == "anthropic" else t.to_openai_schema()
        for t in tools_list
    ]

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # This is the "kill switch" for buffering
        "Connection": "keep-alive",
        "Transfer-Encoding": "chunked"
    }

    if stream:
        async def sse_generator() -> AsyncIterator[str]:
            full_content: list[str] = []
            try:
                async for chunk in provider.stream(
                    messages=llm_messages,
                    model=conv.model,
                    system_prompt=conv.system_prompt,
                    tools=tool_schemas,
                ):
                    full_content.append(chunk)
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
                yield "data: [DONE]\n\n"
                if full_content:
                    async with get_dynamodb_resource() as ddb:
                        tbl = await ddb.Table(settings.DYNAMODB_TABLE_MESSAGES)
                        save_repo = MessageRepository(tbl)
                        await save_repo.add(
                            conv.id, "assistant",
                            content="".join(full_content),
                            model_used=conv.model,
                        )
            except Exception as e:
                logger.error("streaming error", error=str(e), conversation_id=conv.id)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(sse_generator(), media_type="text/event-stream", headers=headers)

    # Non-streaming: agentic tool loop
    final_response: Optional[MessageResponse] = None
    for _ in range(10):
        llm_resp = await provider.complete(
            messages=llm_messages,
            model=conv.model,
            system_prompt=conv.system_prompt,
            tools=tool_schemas,
        )

        if llm_resp.tool_calls:
            await msg_repo.add(
                conv.id, "assistant",
                content=llm_resp.content,
                tool_calls=llm_resp.tool_calls,
                model_used=llm_resp.model,
                token_count=llm_resp.input_tokens + llm_resp.output_tokens,
            )
            llm_messages.append(LLMMessage(
                role="assistant",
                content=llm_resp.content,
                tool_calls=llm_resp.tool_calls,
            ))

            for tc in llm_resp.tool_calls:
                tool_name = tc["function"]["name"]
                tool_args_raw = tc["function"]["arguments"]
                tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
                tool = get_tool(tool_name)

                tool_result = await tool.execute(**tool_args) if tool else f"Tool '{tool_name}' not found"

                await msg_repo.add(
                    conv.id, "tool",
                    content=str(tool_result),
                    tool_call_id=tc["id"],
                )
                llm_messages.append(LLMMessage(
                    role="tool",
                    content=str(tool_result),
                    tool_call_id=tc["id"],
                ))
        else:
            final_response = await msg_repo.add(
                conv.id, "assistant",
                content=llm_resp.content,
                model_used=llm_resp.model,
                token_count=llm_resp.input_tokens + llm_resp.output_tokens,
            )
            break

    if not final_response:
        raise HTTPException(status_code=500, detail={
            "error": {"code": "tool_loop_exceeded", "message": "Max tool iterations exceeded", "details": {}}
        })

    return final_response


@router.delete(
    "/conversations/{conversation_id}/messages",
    status_code=204,
    summary="Clear messages",
    tags=["Chat"],
)
async def clear_messages(
    conversation_id: str,
    conv_repo: ConversationRepository = Depends(get_conv_repo),
    msg_repo: MessageRepository = Depends(get_msg_repo),
    user: UserClaims = Depends(get_current_user),
):
    await _get_owned_conversation(conversation_id, user.sub, conv_repo)
    await msg_repo.delete_all(conversation_id)
