from __future__ import annotations

import base64
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional

from boto3.dynamodb.conditions import Key

from app.models.db import new_uuid, utcnow
from app.schemas.message import MessageResponse
from app.llm.base import LLMMessage


def _item_to_response(item: dict) -> MessageResponse:
    token_count = item.get("token_count")
    if isinstance(token_count, Decimal):
        token_count = int(token_count)
    return MessageResponse(
        id=item["id"],
        conversation_id=item["conversation_id"],
        role=item["role"],
        content=item.get("content"),
        tool_calls=list(item["tool_calls"]) if item.get("tool_calls") is not None else None,
        tool_call_id=item.get("tool_call_id"),
        model_used=item.get("model_used"),
        token_count=token_count,
        created_at=datetime.fromisoformat(item["created_at"]),
    )


def _encode_cursor(key: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode_cursor(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())


class MessageRepository:
    def __init__(self, table):
        self.table = table

    async def list(
        self, conversation_id: str, limit: int, before_cursor: Optional[str]
    ) -> tuple[list[MessageResponse], bool, Optional[str]]:
        kwargs: dict = {
            "KeyConditionExpression": Key("conversation_id").eq(conversation_id),
            "ScanIndexForward": False,
            "Limit": limit + 1,
        }
        if before_cursor:
            kwargs["ExclusiveStartKey"] = _decode_cursor(before_cursor)

        resp = await self.table.query(**kwargs)
        items = resp.get("Items", [])

        has_more = len(items) > limit
        items = items[:limit]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = _encode_cursor(
                {"conversation_id": last["conversation_id"], "sort_key": last["sort_key"]}
            )

        return [_item_to_response(item) for item in items], has_more, next_cursor

    async def add(
        self,
        conversation_id: str,
        role: str,
        content: Optional[str] = None,
        tool_calls=None,
        tool_call_id: Optional[str] = None,
        model_used: Optional[str] = None,
        token_count: Optional[int] = None,
    ) -> MessageResponse:
        now = utcnow()
        now_iso = now.isoformat()
        msg_id = new_uuid()
        sort_key = f"{now_iso}#{msg_id}"

        item: dict = {
            "id": msg_id,
            "conversation_id": conversation_id,
            "sort_key": sort_key,
            "role": role,
            "created_at": now_iso,
        }
        if content is not None:
            item["content"] = content
        if tool_calls is not None:
            item["tool_calls"] = tool_calls
        if tool_call_id is not None:
            item["tool_call_id"] = tool_call_id
        if model_used is not None:
            item["model_used"] = model_used
        if token_count is not None:
            item["token_count"] = token_count

        await self.table.put_item(Item=item)
        return _item_to_response(item)

    async def get_history(self, conversation_id: str, max_messages: int) -> list[LLMMessage]:
        resp = await self.table.query(
            KeyConditionExpression=Key("conversation_id").eq(conversation_id),
            ScanIndexForward=False,
            Limit=max_messages,
        )
        items = list(reversed(resp.get("Items", [])))
        return [
            LLMMessage(
                role=item["role"],
                content=item.get("content"),
                tool_calls=list(item["tool_calls"]) if item.get("tool_calls") is not None else None,
                tool_call_id=item.get("tool_call_id"),
            )
            for item in items
        ]

    async def delete_all(self, conversation_id: str) -> int:
        count = 0
        kwargs: dict = {
            "KeyConditionExpression": Key("conversation_id").eq(conversation_id),
            "ProjectionExpression": "conversation_id, sort_key",
        }
        while True:
            resp = await self.table.query(**kwargs)
            items = resp.get("Items", [])
            if items:
                async with self.table.batch_writer() as batch:
                    for item in items:
                        await batch.delete_item(
                            Key={
                                "conversation_id": item["conversation_id"],
                                "sort_key": item["sort_key"],
                            }
                        )
                count += len(items)
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return count
