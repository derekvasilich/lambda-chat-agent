import json
from typing import Optional, AsyncIterator
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.database import get_db, AsyncSessionLocal
from app.models.db import Conversation, Message
from app.schemas.message import SendMessageRequest, MessageResponse, MessageListResponse
from app.auth import get_current_user, UserClaims
from app.llm import get_provider, LLMMessage
from app.tools.registry import get_tools_for_conversation, get_tool
from app.routers.conversations import _get_owned_conversation
from app.middleware.rate_limit import limiter, rate_limit_string
from app.config import settings
import structlog

logger = structlog.get_logger()
router = APIRouter()


def _db_message_to_llm(msg: Message) -> LLMMessage:
    return LLMMessage(
        role=msg.role,
        content=msg.content,
        tool_calls=msg.tool_calls,
        tool_call_id=msg.tool_call_id,
    )


async def _get_history(conv: Conversation, db: AsyncSession) -> list[Message]:
    limit = conv.max_history_messages or settings.MAX_HISTORY_MESSAGES
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    msgs = result.scalars().all()
    return list(reversed(msgs))


async def _save_message(
    db: AsyncSession,
    conversation_id: str,
    role: str,
    content: Optional[str] = None,
    tool_calls=None,
    tool_call_id: Optional[str] = None,
    model_used: Optional[str] = None,
    token_count: Optional[int] = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        model_used=model_used,
        token_count=token_count,
    )
    db.add(msg)
    await db.flush()
    return msg


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="List messages",
    tags=["Chat"],
)
async def list_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = Query(None, description="Cursor: message ID to paginate before"),
    db: AsyncSession = Depends(get_db),
    user: UserClaims = Depends(get_current_user),
):
    await _get_owned_conversation(conversation_id, user.sub, db)

    query = select(Message).where(Message.conversation_id == conversation_id)

    if before:
        cursor_msg = await db.get(Message, before)
        if cursor_msg:
            query = query.where(Message.created_at < cursor_msg.created_at)

    query = query.order_by(Message.created_at.asc()).limit(limit + 1)
    result = await db.execute(query)
    msgs = result.scalars().all()

    has_more = len(msgs) > limit
    msgs = list(reversed(msgs[:limit]))

    return MessageListResponse(
        items=[MessageResponse.model_validate(m) for m in msgs],
        has_more=has_more,
        next_cursor=msgs[0].id if has_more and msgs else None,
    )


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
    db: AsyncSession = Depends(get_db),
    user: UserClaims = Depends(get_current_user),
):
    conv = await _get_owned_conversation(conversation_id, user.sub, db)
    request.state.user = user

    # Save user message
    user_msg = await _save_message(db, conv.id, "user", content=body.content)

    history = await _get_history(conv, db)
    llm_messages = [_db_message_to_llm(m) for m in history]

    provider = get_provider(conv.provider)
    tools_list = get_tools_for_conversation(conv.enabled_tools or [])
    tool_schemas = [t.to_anthropic_schema() if conv.provider == "anthropic" else t.to_openai_schema() for t in tools_list]

    if stream:
        await db.commit()

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
                    async with AsyncSessionLocal() as save_db:
                        await _save_message(
                            save_db, conv.id, "assistant",
                            content="".join(full_content),
                            model_used=conv.model,
                        )
                        await save_db.commit()
            except Exception as e:
                logger.error("streaming error", error=str(e), conversation_id=conv.id)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    # Non-streaming: run agentic tool loop
    final_response = None
    for _ in range(10):  # max tool iterations
        llm_resp = await provider.complete(
            messages=llm_messages,
            model=conv.model,
            system_prompt=conv.system_prompt,
            tools=tool_schemas,
        )

        if llm_resp.tool_calls:
            # Save assistant message with tool calls
            asst_msg = await _save_message(
                db, conv.id, "assistant",
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

            # Execute each tool and append results
            for tc in llm_resp.tool_calls:
                tool_name = tc["function"]["name"]
                tool_args_raw = tc["function"]["arguments"]
                tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
                tool = get_tool(tool_name)

                if tool:
                    tool_result = await tool.execute(**tool_args)
                else:
                    tool_result = f"Tool '{tool_name}' not found"

                await _save_message(
                    db, conv.id, "tool",
                    content=str(tool_result),
                    tool_call_id=tc["id"],
                )
                llm_messages.append(LLMMessage(
                    role="tool",
                    content=str(tool_result),
                    tool_call_id=tc["id"],
                ))
        else:
            final_response = await _save_message(
                db, conv.id, "assistant",
                content=llm_resp.content,
                model_used=llm_resp.model,
                token_count=llm_resp.input_tokens + llm_resp.output_tokens,
            )
            break

    if not final_response:
        raise HTTPException(status_code=500, detail={
            "error": {"code": "tool_loop_exceeded", "message": "Max tool iterations exceeded", "details": {}}
        })

    await db.commit()
    await db.refresh(final_response)
    return MessageResponse.model_validate(final_response)


@router.delete(
    "/conversations/{conversation_id}/messages",
    status_code=204,
    summary="Clear messages",
    tags=["Chat"],
)
async def clear_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserClaims = Depends(get_current_user),
):
    await _get_owned_conversation(conversation_id, user.sub, db)
    await db.execute(
        delete(Message).where(Message.conversation_id == conversation_id)
    )
    await db.commit()
