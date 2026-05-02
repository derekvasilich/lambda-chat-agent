import base64
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from app.models.db import new_uuid, utcnow
from app.schemas.config import ConversationConfigUpdate
from app.schemas.conversation import ConversationCreate, ConversationResponse
from app.config import settings


def _item_to_response(item: dict) -> ConversationResponse:
    mhm = item.get("max_history_messages")
    return ConversationResponse(
        id=item["id"],
        user_id=item["user_id"],
        title=item["title"],
        system_prompt=item.get("system_prompt"),
        provider=item["provider"],
        model=item["model"],
        max_history_messages=int(mhm) if mhm is not None else None,
        enabled_tools=list(item.get("enabled_tools", [])),
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(item["updated_at"]),
        first_message=None,
    )


def _encode_cursor(key: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode_cursor(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())


class ConversationRepository:
    def __init__(self, table, messages_table):
        self.table = table
        self.messages_table = messages_table

    async def get(self, id: str, user_id: str) -> Optional[ConversationResponse]:
        resp = await self.table.get_item(Key={"id": id})
        item = resp.get("Item")
        if not item or item.get("user_id") != user_id:
            return None
        return _item_to_response(item)

    async def list(
        self, user_id: str, page_size: int, cursor: Optional[str]
    ) -> tuple[list[ConversationResponse], Optional[str]]:
        kwargs: dict = {
            "IndexName": "user_id-created_at-index",
            "KeyConditionExpression": Key("user_id").eq(user_id),
            "ScanIndexForward": False,
            "Limit": page_size,
        }
        if cursor:
            kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)

        resp = await self.table.query(**kwargs)
        items = resp.get("Items", [])
        # TODO: first_message preview requires a per-item cross-table query — omitted for cost
        convs = [_item_to_response(item) for item in items]

        next_cursor = None
        if "LastEvaluatedKey" in resp:
            next_cursor = _encode_cursor(resp["LastEvaluatedKey"])

        return convs, next_cursor

    async def create(self, user_id: str, data: ConversationCreate) -> ConversationResponse:
        now = utcnow().isoformat()
        item = {
            "id": new_uuid(),
            "user_id": user_id,
            "title": data.title,
            "system_prompt": data.system_prompt or settings.DEFAULT_SYSTEM_PROMPT,
            "provider": data.provider or settings.DEFAULT_LLM_PROVIDER,
            "model": data.model or settings.DEFAULT_MODEL,
            "enabled_tools": [],
            "created_at": now,
            "updated_at": now,
        }
        await self.table.put_item(Item=item)
        return _item_to_response(item)

    async def update_config(
        self, id: str, user_id: str, data: ConversationConfigUpdate
    ) -> Optional[ConversationResponse]:
        now = utcnow().isoformat()
        update_parts = ["#updated_at = :updated_at"]
        expr_values: dict = {":updated_at": now, ":user_id": user_id}
        expr_names: dict = {"#updated_at": "updated_at", "#user_id": "user_id"}

        if data.system_prompt is not None:
            update_parts.append("system_prompt = :system_prompt")
            expr_values[":system_prompt"] = data.system_prompt
        if data.provider is not None:
            update_parts.append("#provider = :provider")
            expr_values[":provider"] = data.provider
            expr_names["#provider"] = "provider"
        if data.model is not None:
            update_parts.append("#model = :model")
            expr_values[":model"] = data.model
            expr_names["#model"] = "model"
        if data.max_history_messages is not None:
            update_parts.append("max_history_messages = :max_history_messages")
            expr_values[":max_history_messages"] = data.max_history_messages
        if data.enabled_tools is not None:
            update_parts.append("enabled_tools = :enabled_tools")
            expr_values[":enabled_tools"] = data.enabled_tools

        try:
            resp = await self.table.update_item(
                Key={"id": id},
                UpdateExpression="SET " + ", ".join(update_parts),
                ConditionExpression="attribute_exists(id) AND #user_id = :user_id",
                ExpressionAttributeValues=expr_values,
                ExpressionAttributeNames=expr_names,
                ReturnValues="ALL_NEW",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise

        return _item_to_response(resp["Attributes"])

    async def set_title(self, id: str, title: str) -> None:
        await self.table.update_item(
            Key={"id": id},
            UpdateExpression="SET title = :title, updated_at = :updated_at",
            ExpressionAttributeValues={
                ":title": title,
                ":updated_at": utcnow().isoformat(),
            },
        )

    async def delete(self, id: str, user_id: str) -> bool:
        try:
            await self.table.delete_item(
                Key={"id": id},
                ConditionExpression="attribute_exists(id) AND user_id = :user_id",
                ExpressionAttributeValues={":user_id": user_id},
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

        await self._delete_conversation_messages(id)
        return True

    async def _delete_conversation_messages(self, conversation_id: str) -> None:
        kwargs: dict = {
            "KeyConditionExpression": Key("conversation_id").eq(conversation_id),
            "ProjectionExpression": "conversation_id, sort_key",
        }
        while True:
            resp = await self.messages_table.query(**kwargs)
            items = resp.get("Items", [])
            if items:
                async with self.messages_table.batch_writer() as batch:
                    for item in items:
                        await batch.delete_item(
                            Key={
                                "conversation_id": item["conversation_id"],
                                "sort_key": item["sort_key"],
                            }
                        )
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
