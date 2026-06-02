import base64
from datetime import datetime
from decimal import Decimal
import json
from typing import Optional

from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

from app.models.db import utcnow
from app.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentUpdate,
)

def _encode_cursor(key: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode_cursor(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())


def _parse_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _item_to_response(item: dict) -> DocumentResponse:
    op_count = item.get("operation_count")
    if isinstance(op_count, Decimal):
        op_count = int(op_count)
    return DocumentResponse(
        object_key=item["object_key"],
        user_id=item["user_id"],
        status=item["status"],
        words=item.get("words"),
        extracted_text=item.get("extracted_text"),
        metadata=item.get("metadata"),
        cache_etag=item.get("cache_etag"),
        last_fetched_at=_parse_datetime(item.get("last_fetched_at")),
        operation_count=op_count,
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(item["updated_at"]),
    )


class DocumentRepository:
    def __init__(self, table):
        self.table = table

    async def get(
        self, user_id: str, object_key: str
    ) -> Optional[DocumentResponse]:
        resp = await self.table.get_item(Key={"object_key": object_key})
        item = resp.get("Item")
        if not item or item.get("user_id") != user_id:
            return None
        return _item_to_response(item)

    async def list(
        self, user_id: str, page_size: int, cursor: Optional[str]
    ) -> tuple[list[DocumentResponse], Optional[str]]:
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

    async def create(
        self, user_id: str, data: DocumentCreate
    ) -> DocumentResponse:
        now = utcnow().isoformat()
        item = {
            "object_key": data.object_key,
            "status": data.status,
            "extracted_text": data.extracted_text,
            "etag": data.etag,
            "metadata": data.metadata,
            "created_at": now,
            "updated_at": now,
            "user_id": user_id,
        }
        try:
            await self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(object_key)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ValueError(f"Document with object_key '{data.object_key}' already exists")
            raise
        return _item_to_response(item)

    async def update(
        self, object_key: str, user_id: str, data: DocumentUpdate
    ) -> Optional[DocumentResponse]:
        now = utcnow().isoformat()
        update_parts = ["#updated_at = :updated_at"]
        expr_values: dict = {":updated_at": now, ":user_id": user_id}
        expr_names: dict = {"#updated_at": "updated_at", "#user_id": "user_id"}

        if data.status is not None:
            update_parts.append("#status = :status")
            expr_values[":status"] = data.status
            expr_names["#status"] = "status"
        if data.extracted_text is not None:
            update_parts.append("#extracted_text = :extracted_text")
            expr_values[":extracted_text"] = data.extracted_text
            expr_names["#extracted_text"] = "extracted_text"
        if data.metadata is not None:
            update_parts.append("#metadata = :metadata")
            expr_values[":metadata"] = data.metadata
            expr_names["#metadata"] = "metadata"

        try:
            resp = await self.table.update_item(
                Key={"object_key": object_key},
                UpdateExpression="SET " + ", ".join(update_parts),
                ConditionExpression="attribute_exists(object_key) AND #user_id = :user_id",
                ExpressionAttributeValues=expr_values,
                ExpressionAttributeNames=expr_names,
                ReturnValues="ALL_NEW",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise

        return _item_to_response(resp["Attributes"])

    async def update_cache_metadata(
        self,
        object_key: str,
        cache_etag: Optional[str],
        operation_count: int,
    ) -> Optional[DocumentResponse]:
        now = utcnow().isoformat()
        expr_values: dict = {
            ":fetched_at": now,
            ":updated_at": now,
            ":op_count": operation_count,
        }
        update_parts = [
            "last_fetched_at = :fetched_at",
            "updated_at = :updated_at",
            "operation_count = :op_count",
        ]
        if cache_etag is not None:
            update_parts.append("cache_etag = :etag")
            expr_values[":etag"] = cache_etag

        try:
            resp = await self.table.update_item(
                Key={"object_key": object_key},
                UpdateExpression="SET " + ", ".join(update_parts),
                ConditionExpression="attribute_exists(object_key)",
                ExpressionAttributeValues=expr_values,
                ReturnValues="ALL_NEW",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return _item_to_response(resp["Attributes"])

    async def delete(self, object_key: str) -> bool:
        try:
            await self.table.delete_item(
                Key={"object_key": object_key},
                ConditionExpression="attribute_exists(object_key)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True
    
