from datetime import datetime
from decimal import Decimal
from typing import Optional

from botocore.exceptions import ClientError

from app.models.db import utcnow
from app.schemas.spec_source import (
    AuthConfig,
    SpecSourceCreate,
    SpecSourceResponse,
)


def _parse_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _item_to_response(item: dict) -> SpecSourceResponse:
    op_count = item.get("operation_count")
    if isinstance(op_count, Decimal):
        op_count = int(op_count)
    return SpecSourceResponse(
        id=item["id"],
        url=item["url"],
        description=item["description"],
        auth=item["auth"],
        cache_etag=item.get("cache_etag"),
        last_fetched_at=_parse_datetime(item.get("last_fetched_at")),
        operation_count=op_count,
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(item["updated_at"]),
    )


class SpecSourceRepository:
    def __init__(self, table):
        self.table = table

    async def get(self, id: str) -> Optional[SpecSourceResponse]:
        resp = await self.table.get_item(Key={"id": id})
        item = resp.get("Item")
        if not item:
            return None
        return _item_to_response(item)

    async def list(self) -> list[SpecSourceResponse]:
        resp = await self.table.scan()
        items = resp.get("Items", [])
        return [_item_to_response(item) for item in items]

    async def create(self, data: SpecSourceCreate) -> SpecSourceResponse:
        now = utcnow().isoformat()
        item = {
            "id": data.id,
            "url": data.url,
            "description": data.description,
            "auth": data.auth.model_dump(),
            "created_at": now,
            "updated_at": now,
        }
        try:
            await self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(id)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ValueError(f"Spec source '{data.id}' already exists")
            raise
        return _item_to_response(item)

    async def update_cache_metadata(
        self,
        id: str,
        cache_etag: Optional[str],
        operation_count: int,
    ) -> Optional[SpecSourceResponse]:
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
                Key={"id": id},
                UpdateExpression="SET " + ", ".join(update_parts),
                ConditionExpression="attribute_exists(id)",
                ExpressionAttributeValues=expr_values,
                ReturnValues="ALL_NEW",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return _item_to_response(resp["Attributes"])

    async def delete(self, id: str) -> bool:
        try:
            await self.table.delete_item(
                Key={"id": id},
                ConditionExpression="attribute_exists(id)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True
